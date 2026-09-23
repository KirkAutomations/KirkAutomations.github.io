"""Clean, network-free verification of final CSV and machine-readable evidence."""
from pathlib import Path
import csv, hashlib, json, re, sys
import shapefile
from shapely.geometry import Point, shape
OUT=Path(__file__).resolve().parent
HEADERS=["restaurant name","street address","city/state/ZIP","source URL(s)","boundary-verification method/evidence","Sports Likelihood","brief factual sports rationale"]
GEOID="2634260"
def norm(s): return re.sub(r"[^a-z0-9]+"," ",s.lower()).strip()
def fail(msg,errors): errors.append(msg)
def main():
 errors=[]
 csv_path=OUT/"restaurants.csv"
 with csv_path.open(encoding="utf-8-sig",newline="") as f:
  reader=csv.DictReader(f); actual=reader.fieldnames; rows=list(reader)
 if actual!=HEADERS: fail(f"header mismatch: {actual}",errors)
 if len(rows)!=51: fail(f"row count {len(rows)} != 51",errors)
 blanks=[(i+2,h) for i,r in enumerate(rows) for h in HEADERS if not (r.get(h) or "").strip()]
 if blanks: fail(f"blank required cells: {blanks[:20]}",errors)
 addresses=[norm(r["street address"]+" "+r["city/state/ZIP"]) for r in rows]
 dup=sorted({a for a in addresses if addresses.count(a)>1})
 if dup: fail(f"duplicate normalized addresses: {dup}",errors)
 bad_sports=[r["Sports Likelihood"] for r in rows if r["Sports Likelihood"] not in {"High","Medium","Low"}]
 if bad_sports: fail(f"invalid Sports Likelihood values: {bad_sports}",errors)
 if any("http" not in r["source URL(s)"] or "census.gov" not in r["source URL(s)"] for r in rows): fail("one or more rows lacks official/boundary URLs",errors)
 # Load the same authoritative shapefile independently.
 shp=next((OUT/"tiger_unsd").glob("*.shp")); rd=shapefile.Reader(str(shp)); fields=[f[0] for f in rd.fields[1:]]; district=None
 for sr in rd.iterShapeRecords():
  rec=dict(zip(fields,sr.record))
  if str(rec.get("GEOID"))==GEOID: district=shape(sr.shape.__geo_interface__); break
 if district is None: fail("Troy district feature missing",errors)
 geos=json.loads((OUT/"geocode_evidence.json").read_text(encoding="utf-8"))["records"]
 if len(geos)!=51: fail(f"geocode evidence count {len(geos)} != 51",errors)
 geo_by_addr={norm(g["input_address"]):g for g in geos}
 point_fail=[]; low_score=[]; missing_geo=[]
 for r in rows:
  key=norm(r["street address"]+" "+r["city/state/ZIP"])
  g=geo_by_addr.get(key)
  if not g: missing_geo.append(key); continue
  c=g["chosen"]; p=Point(float(c["longitude"]),float(c["latitude"]))
  if not district.covers(p): point_fail.append(key)
  if float(c["score"])<75: low_score.append((key,c["score"]))
 if missing_geo: fail(f"missing geocodes: {missing_geo}",errors)
 if point_fail: fail(f"outside polygon: {point_fail}",errors)
 if low_score: fail(f"geocode score below 75: {low_score}",errors)
 checks=json.loads((OUT/"source_checks.json").read_text(encoding="utf-8"))["checks"]
 if len(checks)!=51: fail(f"source-check count {len(checks)} != 51",errors)
 source_by_key={(norm(x["restaurant_name"]),norm(x["street"])):x for x in checks}
 missing_sources=[]; dead_sources=[]
 for r in rows:
  x=source_by_key.get((norm(r["restaurant name"]),norm(r["street address"])))
  if not x: missing_sources.append(r["restaurant name"]+" @ "+r["street address"]); continue
  if x.get("status") in (404,410) or not x.get("reachable"): dead_sources.append({"restaurant":r["restaurant name"],"status":x.get("status"),"error":x.get("error")})
 if missing_sources: fail(f"missing source evidence: {missing_sources}",errors)
 if dead_sources: fail(f"dead/unreachable official sources: {dead_sources}",errors)
 geojson=json.loads((OUT/"boundary_checks.geojson").read_text(encoding="utf-8"))
 if len(geojson.get("features",[]))!=51: fail("boundary_checks.geojson does not have 51 features",errors)
 city_path=OUT/"parent_independent_qa_summary.json"
 city=json.loads(city_path.read_text(encoding="utf-8")) if city_path.exists() else {}
 if not city.get("PASS") or city.get("geocoded_rows")!=51 or not city.get("all_geocoded_points_inside_official_polygon"):
  fail("City of Troy independent boundary/geocoder QA is missing or did not pass",errors)
 report=(OUT/"report.md").read_text(encoding="utf-8")
 for phrase in ("Final restaurant rows: **51**","Census TIGER/Line point-in-polygon passes: **51 of 51**","City of Troy official polygon point-in-polygon passes: **51 of 51**","All 51 Esri-geocoded points"):
  if phrase not in report: fail(f"report missing exact outcome: {phrase}",errors)
 summary={"status":"pass" if not errors else "fail","csv_sha256":hashlib.sha256(csv_path.read_bytes()).hexdigest(),"data_rows":len(rows),"exact_headers":actual==HEADERS,"blank_required_cells":len(blanks),"unique_normalized_addresses":len(set(addresses)),"source_records":len(checks),"source_failures":len(dead_sources)+len(missing_sources),"geocoded_rows":len(geos),"census_point_in_polygon_passes":len(rows)-len(point_fail)-len(missing_geo),"city_of_troy_geocoded_rows":city.get("geocoded_rows",0),"city_of_troy_point_in_polygon_passes":51-len(city.get("outside_or_unmatched_rows",[])) if city else 0,"sports_likelihood_counts":{x:sum(r["Sports Likelihood"]==x for r in rows) for x in ("High","Medium","Low")},"errors":errors}
 (OUT/"qa_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 print(json.dumps(summary,indent=2)); return 0 if not errors else 1
if __name__=="__main__": sys.exit(main())
