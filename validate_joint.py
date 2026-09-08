"""Generic validation for the Jiangxi-Zhejiang joint experiment."""
import json
from itertools import combinations
from pathlib import Path
import shapely
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from soften_angles import filter_parts, acute_vertices
from generate_map import topology_signature

ROOT=Path(__file__).parent

def parse(path):
    rings=[]
    for part in path.split("M")[1:]:
        points=[tuple(map(float,p.split(","))) for p in part.split("Z")[0].strip().replace("L","").split()]
        rings.append(Polygon(points))
    out=rings[0]
    for ring in rings[1:]:
        out=out.symmetric_difference(ring)
    return out

def edges(path):
    for part in path.split("M")[1:]:
        pts=[tuple(map(float,p.split(","))) for p in part.split("Z")[0].strip().replace("L","").split()]
        yield from zip(pts,pts[1:])

if __name__=="__main__":
    data=json.loads((ROOT/"dist/map-data.js").read_text().split(" = ",1)[1].rstrip(";\n"))
    reference=json.loads((ROOT/"dist/reference-data.js").read_text().split(" = ",1)[1].rstrip(";\n"))
    assert data["sourceSha256"]==reference["sha256"]
    assert len(reference["regions"])==22, len(reference["regions"])
    real={r["id"]:parse(r["path"]) for r in reference["regions"]}
    province_by_id={r["id"]:r.get("province") for r in reference["regions"]}
    expected={(a,b) for a,b in combinations(sorted(real),2) if real[a].boundary.intersection(real[b].boundary).length>1e-6}
    cross={(a,b) for a,b in expected if province_by_id[a]!=province_by_id[b]}
    assert cross, "joint coverage has no Jiangxi-Zhejiang shared city boundary"
    print("reference:",len(real),"regions;",len(expected),"adjacencies;",len(cross),"cross-province adjacencies")

    for mode in data["variants"]:
        polys={r["id"]:parse(r["variants"][mode]["path"]) for r in data["regions"]}
        assert set(polys)==set(real)
        assert all(p.is_valid and p.area>0 for p in polys.values())
        assert shapely.coverage_is_valid(list(polys.values()))
        expected_polys=filter_parts(list(real.values()))[0] if mode in ("softened","compact","shared") else list(real.values())
        assert topology_signature([polys[k] for k in real])==topology_signature(expected_polys)
        actual={(a,b) for a,b in combinations(sorted(polys),2) if polys[a].boundary.intersection(polys[b].boundary).length>1e-6}
        assert actual==expected
        merged=unary_union(list(polys.values()))
        assert abs(sum(p.area for p in polys.values())-merged.area)<1e-6
        for r in data["regions"]:
            assert polys[r["id"]].contains(Point(r["variants"][mode]["label"]))
            for a,b in edges(r["variants"][mode]["path"]):
                dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1])
                assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
        if mode in ("softened","compact","shared"):
            assert not any(acute_vertices(p) for p in polys.values())
        print(mode,": coverage valid, topology preserved, seam continuous")

    shared={r["id"]:parse(r["variants"]["shared"]["path"]) for r in data["regions"]}
    cross_shared={(a,b) for a,b in expected if province_by_id[a]!=province_by_id[b] and shared[a].boundary.intersection(shared[b].boundary).length>1e-6}
    assert cross_shared==cross
    print("final shared map preserves all cross-province seams:",sorted(cross_shared))
