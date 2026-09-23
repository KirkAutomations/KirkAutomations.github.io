# Troy School District restaurant dataset

Generated: 2026-09-23T20:16:07+00:00

## Result

- Final restaurant rows: **51**
- Unique normalized physical addresses: **51**
- Census TIGER/Line point-in-polygon passes: **51 of 51**
- City of Troy official polygon point-in-polygon passes: **51 of 51** (15 coordinates from the City locator; 36 preserved Esri-coordinate fallbacks on this run).
- Official-source URLs tested: **51**; reachable or explicitly automation-blocked: **51**
- Pages where the fetched body exposed either an address number or restaurant-name token: **48**
- Sports Likelihood: **2 High, 12 Medium, 37 Low**

## Methodology

1. Began with OpenStreetMap only as a discovery inventory, then manually curated physical restaurant locations and replaced discovery links with each restaurant's official site or official brand location page.
2. Requested every official URL live and recorded status, redirect target, title, content hash, and lightweight address/name checks in `source_checks.json`. An official current location page is the operation evidence. A 401/403/405/429 is retained as reachable-but-automation-blocked, not as a successful content read.
3. Geocoded every complete street address with the public Esri World Geocoding Service. The selected candidate had to score at least 75 and fall in the district polygon. Full requests and candidate responses are in `geocode_evidence.json`.
4. Loaded the U.S. Census Bureau 2025 TIGER/Line unified school district shapefile and selected **Troy School District, Michigan, GEOID 2634260**. Every selected geocode was tested with polygon `covers`, so points exactly on the legal boundary also pass.
5. Checked all 51 coordinates against the City of Troy's separate official Administrative/MapServer/3 feature `NAME='TROY SCHOOLS'`. The municipal Site Address Locator was attempted first; rows without a returned candidate used the already-preserved Esri geocode. Exact coordinate-source counts are in `parent_independent_qa_results.csv` and `parent_independent_qa_summary.json`.
6. Enforced the exact CSV header, 51 rows, nonblank cells, permitted likelihood values, URL syntax, and unique normalized physical addresses. A separate clean verifier reproduces the TIGER polygon and file-integrity checks and requires the City cross-check to pass.

## Sources

- Boundary: U.S. Census Bureau, 2025 TIGER/Line Unified School Districts (Michigan): https://www2.census.gov/geo/tiger/TIGER2025/UNSD/tl_2025_26_unsd.zip
- Boundary feature: Troy School District, GEOID 2634260; bounds [-83.20768, 42.53977, -83.088776, 42.624208].
- Independent boundary cross-check: City of Troy official school-district map layer, https://gis1.troymi.gov/portal/sharing/servers/2fe73fda32db489ebc93d603e84ad1f7/rest/services/Administrative/MapServer/3 and public map https://cityoftroy.maps.arcgis.com/apps/webappviewer/index.html?id=55db916864ba43e0b15fd3470f67e4ef
- Restaurant operation/address: the official URL preserved on each CSV row. Live request evidence is in `source_checks.json`.
- Geocoding: Esri World Geocoding Service. Chosen candidate scores range from **98.2 to 100.0**.

## Verification outcomes

- Header is exactly the seven requested columns.
- All required cells are nonblank.
- All 51 normalized physical addresses are unique.
- All 51 Esri-geocoded points are inside or on the Census district polygon.
- All 51 points are inside or on the City's official `TROY SCHOOLS` polygon; this run used 15 City-locator coordinates and 36 preserved Esri-coordinate fallbacks.
- HTTP status distribution from the live official-source pass: **{'200': 45, '403': 6}**.
- Sports labels are conservative. High is reserved for official sports-bar identification. Medium reflects a documented full-service bar/brewery/lounge/group-dining format without claiming guaranteed game-day programming. Low means the official material does not support a sports-viewing inference.

## Caveats

- The City locator returned no candidate for 36 rows during the latest clean run; those rows reused their preserved high-score Esri coordinates for the independent City-polygon test.

- Restaurant operation can change after the generated timestamp. Re-run `python run_pipeline.py` to repeat the complete live build and both boundary-verification passes.
- Some official sites use JavaScript, bot controls, or access-denied responses; those cases remain visible in `source_checks.json` rather than being silently treated as successful page reads.
- TIGER/Line is the authoritative Census representation of the unified school district boundary, not an enrollment/attendance guarantee for a particular parcel. Parcel-level edge cases should be confirmed with Troy School District.
- Geocoding is address-based. The evidence preserves scores, matched addresses, coordinates, all returned candidates, and the exact point-in-polygon result.
