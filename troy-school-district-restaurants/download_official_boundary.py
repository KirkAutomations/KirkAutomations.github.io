from pathlib import Path
import json, requests
OUT=Path(__file__).resolve().parent
url='https://gis1.troymi.gov/portal/sharing/servers/2fe73fda32db489ebc93d603e84ad1f7/rest/services/Administrative/MapServer/3/query'
params={'where':"NAME='TROY SCHOOLS'",'outFields':'*','returnGeometry':'true','outSR':'4326','f':'geojson'}
r=requests.get(url,params=params,timeout=60)
r.raise_for_status()
data=r.json()
if len(data.get('features',[])) != 1: raise SystemExit(data)
(OUT/'city_of_troy_school_district.geojson').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({'features':len(data['features']),'properties':data['features'][0]['properties'],'source':r.url},indent=2))
