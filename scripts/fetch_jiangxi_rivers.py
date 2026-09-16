import pyogrio,json,shapely,os,argparse
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);cache=ap.parse_args().cache;cache.mkdir(parents=True,exist_ok=True)
os.environ['GDAL_HTTP_TIMEOUT']='60'
os.environ['GDAL_DISABLE_READDIR_ON_OPEN']='EMPTY_DIR'
u='https://github.com/spatialthoughts/cloud-native-geospatial/releases/download/hydrorivers/hydrorivers.fgb'
from pyogrio.raw import read
meta,fid,geo,fields=read('/vsicurl/'+u,bbox=(113.3,24.3,118.7,30.3))
print(meta, len(geo),flush=True)
features=[]
for i,g in enumerate(geo):
 p={k:(v[i].item() if hasattr(v[i],'item') else v[i]) for k,v in zip(meta['fields'],fields)}
 features.append({'type':'Feature','geometry':shapely.geometry.mapping(shapely.from_wkb(g)),'properties':p})
open(cache/'hydrorivers.json','w').write(json.dumps({'type':'FeatureCollection','features':features}))
print('saved',len(features),flush=True)
