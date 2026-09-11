"""Verify the 85-unit baseline, complete references and balanced delivery."""
import json,hashlib
from shapely.ops import unary_union
import shapely
from generate_map import ROOT,geometry_from_path,polygon_parts,adjacent
from soften_angles import acute_vertices
from validate_balanced import validate,turn_count
from build_east import source

def run():
    oldtext=(ROOT/'dist/south-data.js').read_text();old=json.loads(oldtext.split(' = ',1)[1].split(';\n')[0]);oldrefs=json.loads(oldtext.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions']
    text=(ROOT/'dist/special-data.js').read_text();d=json.loads(text.split(' = ',1)[1].split(';\n')[0]);refs=json.loads(text.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions'];report=json.loads((ROOT/'dist/special-report.json').read_text())
    assert len(d['regions'])==85 and len({r['id'] for r in d['regions']})==85
    assert report['baseSha256']==hashlib.sha256(oldtext.encode()).hexdigest()
    pp=[geometry_from_path(r['variants']['east']['path']) for r in d['regions']];qq=[geometry_from_path(r['variants']['east']['path']) for r in old['regions']]
    assert all(p.is_valid for p in pp) and shapely.coverage_is_valid(pp)
    changed=[]
    for i,(p,q) in enumerate(zip(pp,qq)):
        if not p.equals(q):changed.append(d['regions'][i]['name'])
        else:assert d['regions'][i]['variants']['east']['label']==old['regions'][i]['variants']['east']['label']
    assert changed==['深圳'],changed
    assert qq[63].symmetric_difference(pp[63]).area<16
    expected=adjacent(qq)
    for j,name in enumerate(['深圳','珠海','嘉兴']):expected.add((next(i for i,r in enumerate(old['regions']) if r['name']==name),82+j))
    assert adjacent(pp)==expected and len(expected)==194
    assert sum(len(acute_vertices(p)) for p in pp)==6
    assert not any(p.interiors for p in polygon_parts(unary_union(pp)))
    assert len(polygon_parts(unary_union(pp)))==len(polygon_parts(unary_union(qq)))+2
    assert len(refs)==85
    for r,o in zip(refs,oldrefs):assert r['path']==o['path']
    for j,(name,kind,filename) in enumerate([('香港','特别行政区','hongkong'),('澳门','特别行政区','macau'),('上海','直辖市','shanghai')]):
        r=d['regions'][82+j];assert r['name']==name and r['administrativeType']==kind and r['fullName']==name+('市' if kind=='直辖市' else '特别行政区')
        _,raw,sha=source(filename+'-source.geojson',name);assert geometry_from_path(refs[82+j]['path']).equals(raw[0]);sr=report['sourceReports'][j];assert sr['sourceSha256']==sha
        if name!='澳门':assert sr['finalMainlandIou']>=.75
        else:assert sr['placement']=='coastal adjacency illustration' and sr['translation']==[9.75,0] and sr['finalMainlandIou']==0
        assert sr['finalMainlandAreaError']<=.15
        assert turn_count(pp[82+j])==[25,7,26][j]
    assert len(report['islands'])==2 and report['islands'][1]['sourceGroupParts']==2
    for island in report['islands']:
        g=geometry_from_path(island['path']);assert pp[-1].covers(g)
        assert g.distance(unary_union(pp[:-1]+[pp[-1].difference(g)]))>=2.5-1e-6
    print('Baseline passed: 85 units, 194 adjacencies, only Shenzhen coastline modified; Macau displacement explicitly reported.')
    validate('special-data.js','special-balanced-data.js','special-balanced-report.json')
if __name__=='__main__':run()
