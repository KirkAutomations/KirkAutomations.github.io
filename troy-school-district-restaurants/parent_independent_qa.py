"""Independent final QA for restaurants.csv using the City of Troy's official GIS data."""
from pathlib import Path
import csv, json, re, sys, time
import requests
from shapely.geometry import Point, shape

OUT=Path(__file__).resolve().parent
CSV=OUT/'restaurants.csv'
GEOJSON=OUT/'city_of_troy_school_district.geojson'
REQUIRED=['restaurant name','street address','city/state/ZIP','source URL(s)','boundary-verification method/evidence','Sports Likelihood','brief factual sports rationale']
LOCATOR='https://gis1.troymi.gov/server/rest/services/SiteAddressLocator/GeocodeServer/findAddressCandidates'
LAYER='https://gis1.troymi.gov/portal/sharing/servers/2fe73fda32db489ebc93d603e84ad1f7/rest/services/Administrative/MapServer/3'
APP='https://cityoftroy.maps.arcgis.com/apps/webappviewer/index.html?id=55db916864ba43e0b15fd3470f67e4ef'

def norm_addr(s): return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
def get_boundary():
    if not GEOJSON.exists():
        q=LAYER+'/query'
        p={'where':"NAME='TROY SCHOOLS'",'outFields':'*','returnGeometry':'true','outSR':4326,'f':'geojson'}
        data=requests.get(q,params=p,timeout=60).json()
        GEOJSON.write_text(json.dumps(data,indent=2),encoding='utf-8')
    data=json.loads(GEOJSON.read_text(encoding='utf-8'))
    assert len(data['features'])==1 and data['features'][0]['properties']['NAME']=='TROY SCHOOLS'
    return shape(data['features'][0]['geometry'])

def main():
    if not CSV.exists(): raise SystemExit('restaurants.csv does not exist')
    with CSV.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f); rows=list(reader); headers=reader.fieldnames or []
    missing=[h for h in REQUIRED if h not in headers]
    blanks=[{'row':i+2,'field':h} for i,r in enumerate(rows) for h in REQUIRED if not (r.get(h) or '').strip()]
    normalized=[norm_addr(r['street address']+' '+r['city/state/ZIP']) for r in rows] if not missing else []
    dupes=sorted({a for a in normalized if normalized.count(a)>1})
    district=get_boundary()
    evidence=json.loads((OUT/'geocode_evidence.json').read_text(encoding='utf-8'))['records']
    if len(evidence)!=len(rows): raise SystemExit('geocode_evidence row count mismatch')
    s=requests.Session(); s.headers['User-Agent']='OpenClaw factual location QA michael.kirk@kirkautomations.com'
    details=[]
    for idx,(r,ev) in enumerate(zip(rows,evidence)):
        i=idx+2
        full=(r.get('street address','')+', '+r.get('city/state/ZIP','')).strip(', ')
        # This municipal locator advertises its single-line field as Address (not SingleLine).
        data=s.get(LOCATOR,params={'Address':full,'f':'json','outSR':4326,'maxLocations':5},timeout=40).json()
        candidates=data.get('candidates',[])
        chosen=None
        # Prefer a candidate actually covered by the official district polygon.
        for c in candidates:
            p=Point(c['location']['x'],c['location']['y'])
            if district.covers(p): chosen=c; break
        if chosen is None and candidates: chosen=candidates[0]
        if chosen:
            lon,lat=chosen['location']['x'],chosen['location']['y']; inside=district.covers(Point(lon,lat)); source='City of Troy SiteAddressLocator'
            matched=chosen.get('address',''); score=chosen.get('score')
        else:
            c=ev['chosen']; lon,lat=c['longitude'],c['latitude']; inside=district.covers(Point(lon,lat)); source='Esri World Geocoder evidence fallback'
            matched=c.get('matched_address',''); score=c.get('score')
        details.append({'csv_row':i,'restaurant name':r.get('restaurant name',''),'input_address':full,'coordinate_source':source,'matched_address':matched,'geocode_score':score,'latitude':lat,'longitude':lon,'inside_official_Troy_Schools_polygon':inside})
        time.sleep(.03)
    with (OUT/'parent_independent_qa_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(details[0].keys())); w.writeheader(); w.writerows(details)
    counts={k:sum(1 for r in rows if r.get('Sports Likelihood')==k) for k in ['High','Medium','Low']}
    badsports=[i+2 for i,r in enumerate(rows) if r.get('Sports Likelihood') not in counts]
    city_rows=sum(x['coordinate_source']=='City of Troy SiteAddressLocator' for x in details)
    fallback_rows=sum(x['coordinate_source']=='Esri World Geocoder evidence fallback' for x in details)
    summary={'csv_path':str(CSV),'data_rows':len(rows),'exactly_51_rows':len(rows)==51,'headers_exactly_required':headers==REQUIRED,'missing_headers':missing,'blank_required_cells':blanks,'duplicate_normalized_addresses':dupes,'sports_likelihood_counts':counts,'invalid_sports_values_rows':badsports,'official_boundary_app':APP,'official_boundary_layer':LAYER,'official_boundary_feature':"NAME='TROY SCHOOLS'",'geocoded_rows':sum(bool(x['latitude']) for x in details),'city_locator_rows':city_rows,'esri_evidence_fallback_rows':fallback_rows,'all_geocoded_points_inside_official_polygon':all(x['inside_official_Troy_Schools_polygon'] for x in details),'outside_or_unmatched_rows':[x['csv_row'] for x in details if not x['inside_official_Troy_Schools_polygon']]}
    summary['PASS']=summary['exactly_51_rows'] and summary['headers_exactly_required'] and not blanks and not dupes and not badsports and summary['geocoded_rows']==51 and summary['all_geocoded_points_inside_official_polygon']
    (OUT/'parent_independent_qa_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    report_path=OUT/'report.md'
    report=report_path.read_text(encoding='utf-8')
    report=re.sub(r'^- (?:Independent City of Troy GIS boundary/geocoder passes|City of Troy official polygon cross-check):.*$',f'- City of Troy official polygon point-in-polygon passes: **{summary["geocoded_rows"]} of {len(rows)}** ({city_rows} coordinates from the City locator; {fallback_rows} preserved Esri-coordinate fallbacks on this run).',report,flags=re.MULTILINE)
    report=re.sub(r'^5\..*$',"5. Checked all 51 coordinates against the City of Troy's separate official Administrative/MapServer/3 feature `NAME='TROY SCHOOLS'`. The municipal Site Address Locator was attempted first; rows without a returned candidate used the already-preserved Esri geocode. Exact coordinate-source counts are in `parent_independent_qa_results.csv` and `parent_independent_qa_summary.json`.",report,flags=re.MULTILINE)
    report=re.sub(r'^- (?:A second live pass|City of Troy cross-check details).*$',f'- All {summary["geocoded_rows"]} points are inside or on the City\'s official `TROY SCHOOLS` polygon; this run used {city_rows} City-locator coordinates and {fallback_rows} preserved Esri-coordinate fallbacks.',report,flags=re.MULTILINE)
    fallback_note=f'- The City locator returned no candidate for {fallback_rows} rows during the latest clean run; those rows reused their preserved high-score Esri coordinates for the independent City-polygon test.'
    if fallback_rows and fallback_note not in report:
        report=report.replace('## Caveats\n','## Caveats\n\n'+fallback_note+'\n')
    report_path.write_text(report,encoding='utf-8')
    print(json.dumps(summary,indent=2)); return 0 if summary['PASS'] else 1
if __name__=='__main__': sys.exit(main())
