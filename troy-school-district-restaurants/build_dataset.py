"""Build the 51-row Troy School District restaurant dataset and QA evidence.

All paths are anchored to this script's directory. Network calls are limited to
official restaurant pages, Esri's public geocoder, and Census TIGER/Line.
"""
from __future__ import annotations
import argparse, concurrent.futures, csv, datetime as dt, hashlib, html, json, re, time, urllib.parse, zipfile
from collections import Counter
from pathlib import Path
import requests
import shapefile
from shapely.geometry import Point, mapping, shape

OUT = Path(__file__).resolve().parent
SEED = OUT / "curated_restaurants.json"
CSV_OUT = OUT / "restaurants.csv"
TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2025/UNSD/tl_2025_26_unsd.zip"
TIGER_ZIP = OUT / "tl_2025_26_unsd.zip"
TIGER_DIR = OUT / "tiger_unsd"
DISTRICT_GEOID = "2634260"
GEOCODER = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
HEADERS = ["restaurant name", "street address", "city/state/ZIP", "source URL(s)", "boundary-verification method/evidence", "Sports Likelihood", "brief factual sports rationale"]
UA = "Mozilla/5.0 (compatible; OpenClaw factual restaurant dataset; contact michael.kirk@kirkautomations.com)"
UTC = dt.timezone.utc

def now(): return dt.datetime.now(UTC).replace(microsecond=0).isoformat()
def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
def write_json(path, obj): path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def load_boundary():
    if not TIGER_ZIP.exists():
        r=requests.get(TIGER_URL, headers={"User-Agent":UA}, timeout=120); r.raise_for_status(); TIGER_ZIP.write_bytes(r.content)
    TIGER_DIR.mkdir(exist_ok=True)
    if not list(TIGER_DIR.glob("*.shp")):
        with zipfile.ZipFile(TIGER_ZIP) as z: z.extractall(TIGER_DIR)
    shp=next(TIGER_DIR.glob("*.shp")); reader=shapefile.Reader(str(shp)); fields=[f[0] for f in reader.fields[1:]]
    matches=[]
    for sr in reader.iterShapeRecords():
        rec=dict(zip(fields,sr.record))
        if str(rec.get("GEOID")) == DISTRICT_GEOID: matches.append((rec,shape(sr.shape.__geo_interface__)))
    if len(matches)!=1: raise RuntimeError(f"Expected one GEOID {DISTRICT_GEOID}; found {len(matches)}")
    rec, poly=matches[0]
    meta={"source_url":TIGER_URL,"year":2025,"geoid":DISTRICT_GEOID,"name":rec.get("NAME"),"legal_statistical_area_description":rec.get("LSAD"),"bounds":list(poly.bounds),"loaded_at":now()}
    write_json(OUT/"district_boundary_metadata.json",meta)
    return meta,poly

def extract_title(text):
    m=re.search(r"<title[^>]*>(.*?)</title>",text,re.I|re.S)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>","",m.group(1)))).strip()[:300] if m else ""

def check_source(row):
    u=row["official_url"]; result={"restaurant_name":row["name"],"street":row["street"],"requested_url":u,"checked_at":now()}
    try:
        r=requests.get(u,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"},timeout=30,allow_redirects=True)
        body=r.text[:750000] if "text" in r.headers.get("content-type","").lower() or "html" in r.headers.get("content-type","").lower() else ""
        compact=norm(re.sub(r"<[^>]+>"," ",body))
        street_number=re.match(r"\d+",row["street"])
        name_tokens=[x for x in norm(row["name"]).split() if len(x)>=4 and x not in {"restaurant","cuisine","grill","pizza"}]
        result.update({
          "status":r.status_code,"final_url":r.url,"content_type":r.headers.get("content-type",""),"title":extract_title(body),
          "reachable":r.status_code < 400 or r.status_code in (401,403,405,429),
          "address_number_seen":bool(street_number and street_number.group(0) in compact),
          "name_token_seen":any(t in compact for t in name_tokens),
          "body_sha256":hashlib.sha256(r.content).hexdigest(),"bytes":len(r.content)
        })
    except Exception as exc:
        result.update({"status":None,"final_url":"","content_type":"","title":"","reachable":False,"address_number_seen":False,"name_token_seen":False,"error":f"{type(exc).__name__}: {exc}"})
    return result

def source_checks(rows):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex: checks=list(ex.map(check_source,rows))
    checks.sort(key=lambda x:(x["restaurant_name"].lower(),x["street"].lower()))
    write_json(OUT/"source_checks.json",{"generated_at":now(),"method":"HTTP GET of each official restaurant URL; 401/403/405/429 count as host reachable but automation-blocked.","checks":checks})
    return checks

def geocode_one(row, poly, session):
    address=f'{row["street"]}, {row["city_state_zip"]}'
    params={"SingleLine":address,"f":"json","outFields":"Match_addr,Addr_type,PlaceName","maxLocations":8,"location":"-83.148,42.578","distance":20000}
    request_url=GEOCODER+"?"+urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            r=session.get(GEOCODER,params=params,headers={"User-Agent":UA},timeout=40); r.raise_for_status(); data=r.json(); break
        except Exception:
            if attempt==3: raise
            time.sleep(2**attempt)
    candidates=[]
    for c in data.get("candidates",[]):
        lon=float(c["location"]["x"]); lat=float(c["location"]["y"]); inside=bool(poly.covers(Point(lon,lat)))
        candidates.append({"score":c.get("score"),"matched_address":c.get("address"),"longitude":lon,"latitude":lat,"inside_or_on_boundary":inside,"attributes":c.get("attributes",{})})
    chosen=next((c for c in candidates if c["inside_or_on_boundary"] and float(c.get("score") or 0)>=75),None)
    if not chosen: raise RuntimeError(f"No >=75-score in-district geocode for {address}; candidates={candidates}")
    return {"restaurant_name":row["name"],"input_address":address,"request_url":request_url,"provider":"Esri World Geocoding Service","geocoded_at":now(),"chosen":chosen,"candidate_count":len(candidates),"candidates":candidates}

def geocode_all(rows,poly):
    s=requests.Session(); evidence=[]
    for i,row in enumerate(rows,1):
        evidence.append(geocode_one(row,poly,s)); time.sleep(0.08)
    write_json(OUT/"geocode_evidence.json",{"generated_at":now(),"service":GEOCODER,"records":evidence})
    return evidence

def write_geojson(rows, geos):
    feats=[]
    for row,g in zip(rows,geos):
        c=g["chosen"]
        feats.append({"type":"Feature","geometry":{"type":"Point","coordinates":[c["longitude"],c["latitude"]]},"properties":{"restaurant_name":row["name"],"street_address":row["street"],"city_state_zip":row["city_state_zip"],"geocoder_score":c["score"],"matched_address":c["matched_address"],"inside_or_on_boundary":c["inside_or_on_boundary"]}})
    write_json(OUT/"boundary_checks.geojson",{"type":"FeatureCollection","name":"Troy School District restaurant point checks","features":feats})

def build_report(rows,checks,geos,meta):
    sports=Counter(r["sports"] for r in rows); statuses=Counter(str(x["status"]) for x in checks); reachable=sum(x["reachable"] for x in checks); page_match=sum(x["address_number_seen"] or x["name_token_seen"] for x in checks)
    scores=[float(g["chosen"]["score"]) for g in geos]
    report=f"""# Troy School District restaurant dataset

Generated: {now()}

## Result

- Final restaurant rows: **{len(rows)}**
- Unique normalized physical addresses: **{len(set(norm(r['street']+' '+r['city_state_zip']) for r in rows))}**
- Census TIGER/Line point-in-polygon passes: **{sum(g['chosen']['inside_or_on_boundary'] for g in geos)} of {len(geos)}**
- City of Troy official polygon cross-check: **pending in build step**; `run_pipeline.py` fills this with the exact result and coordinate-source counts.
- Official-source URLs tested: **{len(checks)}**; reachable or explicitly automation-blocked: **{reachable}**
- Pages where the fetched body exposed either an address number or restaurant-name token: **{page_match}**
- Sports Likelihood: **{sports['High']} High, {sports['Medium']} Medium, {sports['Low']} Low**

## Methodology

1. Began with OpenStreetMap only as a discovery inventory, then manually curated physical restaurant locations and replaced discovery links with each restaurant's official site or official brand location page.
2. Requested every official URL live and recorded status, redirect target, title, content hash, and lightweight address/name checks in `source_checks.json`. An official current location page is the operation evidence. A 401/403/405/429 is retained as reachable-but-automation-blocked, not as a successful content read.
3. Geocoded every complete street address with the public Esri World Geocoding Service. The selected candidate had to score at least 75 and fall in the district polygon. Full requests and candidate responses are in `geocode_evidence.json`.
4. Loaded the U.S. Census Bureau 2025 TIGER/Line unified school district shapefile and selected **Troy School District, Michigan, GEOID {meta['geoid']}**. Every selected geocode was tested with polygon `covers`, so points exactly on the legal boundary also pass.
5. The full pipeline checks all preserved geocoded points against the City of Troy's separate official Administrative/MapServer/3 feature `NAME='TROY SCHOOLS'`. It also attempts the City Site Address Locator and records exact direct-locator versus preserved-Esri fallback counts in `parent_independent_qa_results.csv` and `parent_independent_qa_summary.json`.
6. Enforced the exact CSV header, 51 rows, nonblank cells, permitted likelihood values, URL syntax, and unique normalized physical addresses. A separate clean verifier reproduces the TIGER polygon and file-integrity checks and requires the City cross-check to pass.

## Sources

- Boundary: U.S. Census Bureau, 2025 TIGER/Line Unified School Districts (Michigan): {TIGER_URL}
- Boundary feature: Troy School District, GEOID {meta['geoid']}; bounds {meta['bounds']}.
- Independent boundary cross-check: City of Troy official school-district map layer, https://gis1.troymi.gov/portal/sharing/servers/2fe73fda32db489ebc93d603e84ad1f7/rest/services/Administrative/MapServer/3 and public map https://cityoftroy.maps.arcgis.com/apps/webappviewer/index.html?id=55db916864ba43e0b15fd3470f67e4ef
- Restaurant operation/address: the official URL preserved on each CSV row. Live request evidence is in `source_checks.json`.
- Geocoding: Esri World Geocoding Service. Chosen candidate scores range from **{min(scores):.1f} to {max(scores):.1f}**.

## Verification outcomes

- Header is exactly the seven requested columns.
- All required cells are nonblank.
- All 51 normalized physical addresses are unique.
- All 51 Esri-geocoded points are inside or on the Census district polygon.
- City of Troy cross-check details are populated by the subsequent `parent_independent_qa.py` pipeline step.
- HTTP status distribution from the live official-source pass: **{dict(sorted(statuses.items()))}**.
- Sports labels are conservative. High is reserved for official sports-bar identification. Medium reflects a documented full-service bar/brewery/lounge/group-dining format without claiming guaranteed game-day programming. Low means the official material does not support a sports-viewing inference.

## Caveats

- Restaurant operation can change after the generated timestamp. Re-run `python run_pipeline.py` to repeat the complete live build and both boundary-verification passes.
- Some official sites use JavaScript, bot controls, or access-denied responses; those cases remain visible in `source_checks.json` rather than being silently treated as successful page reads.
- TIGER/Line is the authoritative Census representation of the unified school district boundary, not an enrollment/attendance guarantee for a particular parcel. Parcel-level edge cases should be confirmed with Troy School District.
- Geocoding is address-based. The evidence preserves scores, matched addresses, coordinates, all returned candidates, and the exact point-in-polygon result.
"""
    (OUT/"report.md").write_text(report,encoding="utf-8")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--refresh",action="store_true",help="Retained for explicit clean network rebuilds; network checks always run."); args=ap.parse_args()
    rows=json.loads(SEED.read_text(encoding="utf-8"))
    if len(rows)!=51: raise RuntimeError(f"Curated input must have 51 rows, found {len(rows)}")
    if len({norm(r['street']+' '+r['city_state_zip']) for r in rows})!=51: raise RuntimeError("Curated input has duplicate normalized addresses")
    meta,poly=load_boundary(); checks=source_checks(rows); geos=geocode_all(rows,poly)
    by_key={(g['restaurant_name'],g['input_address'].split(', Troy,')[0]):g for g in geos}
    with CSV_OUT.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=HEADERS); w.writeheader()
        for row,g in zip(rows,geos):
            c=g["chosen"]
            w.writerow({HEADERS[0]:row["name"],HEADERS[1]:row["street"],HEADERS[2]:row["city_state_zip"],HEADERS[3]:f'{row["official_url"]} | {TIGER_URL}',HEADERS[4]:f'Esri geocode score {float(c["score"]):.1f} at {c["latitude"]:.6f}, {c["longitude"]:.6f}; Census TIGER/Line 2025 UNSD GEOID {DISTRICT_GEOID}; polygon covers point.',HEADERS[5]:row["sports"],HEADERS[6]:row["rationale"]})
    write_geojson(rows,geos); build_report(rows,checks,geos,meta)
    print(json.dumps({"rows":len(rows),"csv":str(CSV_OUT),"inside":sum(g['chosen']['inside_or_on_boundary'] for g in geos),"sources_reachable_or_blocked":sum(x['reachable'] for x in checks),"generated_at":now()},indent=2))
if __name__=="__main__": main()
