"""Independent point-in-polygon recheck using saved geocodes and raw TIGER shapefile."""
from pathlib import Path
import json, sys
import shapefile
from shapely.geometry import Point, shape
OUT=Path(__file__).resolve().parent
rd=shapefile.Reader(str(next((OUT/'tiger_unsd').glob('*.shp'))))
fields=[f[0] for f in rd.fields[1:]]; district=None; meta=None
for sr in rd.iterShapeRecords():
 rec=dict(zip(fields,sr.record))
 if str(rec.get('GEOID'))=='2634260': meta=rec; district=shape(sr.shape.__geo_interface__); break
if district is None: raise SystemExit('Troy School District GEOID 2634260 not found')
records=json.loads((OUT/'geocode_evidence.json').read_text(encoding='utf-8'))['records']
checks=[]
for g in records:
 c=g['chosen']; inside=bool(district.covers(Point(float(c['longitude']),float(c['latitude']))))
 checks.append({'restaurant_name':g['restaurant_name'],'input_address':g['input_address'],'latitude':c['latitude'],'longitude':c['longitude'],'inside_or_on_boundary':inside})
result={'district_name':meta.get('NAME'),'district_geoid':meta.get('GEOID'),'boundary_bounds':list(district.bounds),'points_checked':len(checks),'points_inside_or_on_boundary':sum(x['inside_or_on_boundary'] for x in checks),'all_pass':len(checks)==51 and all(x['inside_or_on_boundary'] for x in checks),'checks':checks}
(OUT/'independent_boundary_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
sys.exit(0 if result['all_pass'] else 1)
