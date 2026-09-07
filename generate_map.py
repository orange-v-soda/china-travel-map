"""Original orthogonal cartogram. Run with Python 3, no dependencies."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
ROWS = [
    '....JJJJJJSSKK..',
    '..JJJJJJJJSSKKK.',
    '.JJJJJJJJJSSKKK.',
    '.JJJJJJJJJSSKKK.',
    '.JJJJJJNNNSSSSSS',
    '.YYYYYNNNNSSSSSS',
    'YYYYYYNNNNSSSSSS',
    'PPPYYYYNNNFFTTTT',
    'PPPYYYYYYYFFTTTT',
    'PPPYYXXXXYFFTTTT',
    '.PAAAXXXXYFFFFFF',
    '..AAAAAAAAFFFFFF',
    '..AAAAAAAAFFFFFF',
    '...AAAAAAAFFFFF.',
    '...AAAAGGGGGFFF.',
    '...GGGGGGGGGGG..',
    '....GGGGGGGGG...',
    '.....GGGGGGG....',
    '......GGGG......',
]
META = {
 'J': ('360400','九江',5.2,2.5), 'K': ('360200','景德镇',13.5,2.1),
 'S': ('361100','上饶',12.4,5.6), 'N': ('360100','南昌',8,5.9),
 'Y': ('360900','宜春',3.9,6.1), 'P': ('360300','萍乡',1.5,8.6),
 'X': ('360500','新余',7,10), 'T': ('360600','鹰潭',14,8.5),
 'A': ('360800','吉安',6.1,12.4), 'F': ('361000','抚州',12.5,12.1),
 'G': ('360700','赣州',9.2,16.3),
}
EXPECTED = {'J':'NYS','K':'S','S':'NKJTF','N':'JYFS','Y':'NPJXAF','P':'AY','X':'AY','T':'FS','A':'PXGYF','F':'NTGAYS','G':'AF'}

def boundary(cells, keep=None):
    edges=set()
    for x,y in cells:
        p=[(x,y),(x+1,y),(x+1,y+1),(x,y+1)]
        for a,b in zip(p,p[1:]+p[:1]):
            if (b,a) in edges: edges.remove((b,a))
            else: edges.add((a,b))
    following=dict(edges)
    assert len(following)==len(edges), 'pinch point'
    start=min(following); points=[start]; p=following[start]
    while p!=start:
        points.append(p); p=following[p]
    assert len(points)==len(edges), 'disconnected or hole'
    if keep is False:return points
    return [b for a,b,c in zip(points[-1:]+points[:-1],points,points[1:]+points[:1]) if (keep and b in keep) or (b[0]-a[0])*(c[1]-b[1]) != (b[1]-a[1])*(c[0]-b[0])]

def octilinear(points, junctions):
    """Bevel shared degree-two corners consistently; keep triple junctions fixed.

    Half-edge limits prevent neighboring bevels from passing one another.
    The same corner generates the same segment in both incident regions.
    """
    result=[]
    for a,b,c in zip(points[-1:]+points[:-1],points,points[1:]+points[:1]):
        u=(a[0]-b[0],a[1]-b[1]);v=(c[0]-b[0],c[1]-b[1])
        if b in junctions or u[0]*v[1]==u[1]*v[0]:result.append(b);continue
        la=abs(u[0])+abs(u[1]);lc=abs(v[0])+abs(v[1]);r=min(1,la/2,lc/2)
        result.extend([(b[0]+r*u[0]/la,b[1]+r*u[1]/la),(b[0]+r*v[0]/lc,b[1]+r*v[1]/lc)])
    clean=[]
    for p in result:
        if not clean or clean[-1]!=p:clean.append(p)
    if clean[0]==clean[-1]:clean.pop()
    return clean

def polygon_area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2

def generate():
    assert all(len(row)==16 for row in ROWS)
    cells={key:set() for key in META}
    for y,row in enumerate(ROWS):
        for x,key in enumerate(row):
            if key!='.':cells[key].add((x,y))
    adjacency={k:set() for k in META}
    for k,cc in cells.items():
        for x,y in cc:
            for dx,dy in [(0,1),(1,0),(-1,0),(0,-1)]:
                xx,yy=x+dx,y+dy
                if 0<=yy<len(ROWS) and 0<=xx<16:
                    other=ROWS[yy][xx]
                    if other not in ('.',k):adjacency[k].add(other)
    for k in META:
        assert adjacency[k]==set(EXPECTED[k]), (k,adjacency[k],set(EXPECTED[k]))
    from collections import defaultdict
    graph=defaultdict(set)
    for cc in cells.values():
        ring=boundary(cc,False)
        for a,b in zip(ring,ring[1:]+ring[:1]):graph[a].add(b);graph[b].add(a)
    junctions={p for p,n in graph.items() if len(n)>2}
    regions=[]
    for key,(code,name,lx,ly) in META.items():
        points=boundary(cells[key],junctions)
        diagonal=octilinear(points,junctions)
        regions.append(dict(id=code,name=name,points=points,diagonal=diagonal,label=[lx,ly],area=len(cells[key]),diagonalArea=polygon_area(diagonal),neighbors=sorted(META[k][0] for k in adjacency[key])))
    outline=boundary(set.union(*cells.values()),junctions)
    data={'version':'0.2.0','regions':regions,'outline':outline,'diagonalOutline':octilinear(outline,junctions)}
    (ROOT/'dist'/'map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,indent=2)+';\n')
    sizes=[len(c) for c in cells.values()]
    print(f'{len(regions)} regions; {sum(map(len,adjacency.values()))//2} shared-edge adjacencies; no holes or disconnected regions; area ratio {max(sizes)/min(sizes):.2f}:1')

if __name__=='__main__':generate()
