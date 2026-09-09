"""Represent a scattered archipelago with three area-weighted island groups."""
import math
from shapely.geometry import Polygon
from shapely.ops import unary_union
from generate_map import polygon_parts

def fit_groups(source,obstacles,separation=1.0):
    parts=sorted(polygon_parts(source),key=lambda p:(-p.area,p.centroid.x,p.centroid.y))
    pts=[(p.centroid.x,p.centroid.y) for p in parts];weights=[p.area for p in parts]
    centers=[pts[0]]
    while len(centers)<3:
        i=max(range(len(pts)),key=lambda i:weights[i]*min(math.dist(pts[i],c)**2 for c in centers));centers.append(pts[i])
    previous=None
    while True:
        labels=[min(range(3),key=lambda k:math.dist(p,centers[k])) for p in pts]
        if labels==previous:break
        previous=labels
        centers=[tuple(sum(weights[i]*pts[i][axis] for i in range(len(pts)) if labels[i]==k)/sum(weights[i] for i in range(len(pts)) if labels[i]==k) for axis in range(2)) for k in range(3)]
    anchor=centers[0]
    centers=[(anchor[0]+(x-anchor[0])*separation,anchor[1]+(y-anchor[1])*separation) for x,y in centers]
    blocks=[];records=[]
    for k,c in enumerate(centers):
        members=[p for i,p in enumerate(parts) if labels[i]==k];area=sum(p.area for p in members)
        # Compact octagons: 45-degree clipped corners, with minimum visible area.
        vx=sum(p.area*(p.centroid.x-c[0])**2 for p in members)/area
        vy=sum(p.area*(p.centroid.y-c[1])**2 for p in members)/area
        ratio=max(1.,min(1.8,math.sqrt((vx+25)/(vy+25))))
        target=max(450.,area*1.6);w=round(math.sqrt(target*ratio)*2)/2;h=round(math.sqrt(target/ratio)*2)/2
        x,y=[round(v*2)/2 for v in c];cut=round(min(w,h)*.22*2)/2
        def block():return Polygon([(x-w/2+cut,y-h/2),(x+w/2-cut,y-h/2),(x+w/2,y-h/2+cut),(x+w/2,y+h/2-cut),(x+w/2-cut,y+h/2),(x-w/2+cut,y+h/2),(x-w/2,y+h/2-cut),(x-w/2,y-h/2+cut)])
        g=block()
        if g.distance(obstacles)<6:raise ValueError('Island group too close to mainland')
        blocks.append(g);records.append({'center':[x,y],'sourceArea':area,'displayArea':g.area,'sourceParts':len(members)})
    if not all(a.distance(b)>=6 for i,a in enumerate(blocks) for b in blocks[i+1:]):
        if separation>=1.6:raise ValueError('Cannot separate island groups')
        return fit_groups(source,obstacles,round(separation+.05,2))
    return unary_union(blocks),{'method':'area-weighted k-means, 3 clipped rectangles','minimumGap':6,'centerSeparationScale':separation,'groups':records,'sourceArea':source.area,'displayArea':sum(p.area for p in blocks)}
