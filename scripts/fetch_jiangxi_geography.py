import urllib.request,json,re,concurrent.futures,pathlib,math
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--cache',type=pathlib.Path,required=True);P=ap.parse_args().cache;P.mkdir(parents=True,exist_ok=True)
def get(url,name):
 f=P/name
 if not f.exists():
  
  try:
   with urllib.request.urlopen(url,timeout=90) as r:f.write_bytes(r.read())
  except Exception as e:
   print(name,str(e),flush=True);return None
 print(name,f.stat().st_size,flush=True)
 return f
jobs=[('https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_'+n+'.geojson',n+'.json') for n in ['lakes','urban_areas','populated_places']]
h=urllib.request.urlopen('https://www.hydrosheds.org/products/hydrorivers',timeout=30).read().decode()
urls=re.findall(r'https[^"<> ]+HydroRIVERS[^"<> ]+zip',h)

u=next((u for u in urls if 'as' in u and 'shp' in u),None)
# River vector download is handled separately by fetch_jiangxi_rivers.py.
for x in range(208,213):
 for y in range(105,111):jobs.append((f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/8/{x}/{y}.png',f'dem-8-{x}-{y}.png'))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 for f in ex.map(lambda a:get(*a),jobs):pass
