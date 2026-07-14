"""
Pre-render Sentinel-2 (cloud-free median 2026) เป็น XYZ tiles ถาวรลงเครื่อง
- ดาวน์โหลด tile PNG จาก Earth Engine เก็บเป็น ./tiles/{z}/{x}/{y}.png
- ไฟล์ PNG เป็นภาพถาวร ไม่มีวันหมดอายุ (ไม่พึ่ง EE token หลังดาวน์โหลดเสร็จ)
- สร้าง Sentinel2_offline.html (Leaflet) ชี้ไปที่ tiles local + พื้นหลัง Google Satellite

Usage:
    .venv/Scripts/python.exe build_offline_tiles.py --project vongsapat-ki
    .venv/Scripts/python.exe build_offline_tiles.py --project vongsapat-ki --zmax 11
"""
import argparse
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import ee
import requests

START_DATE = "2026-01-01"
END_DATE = "2026-07-14"
CS_THRESHOLD = 0.60
VIS = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.1}
TILE_DIR = "tiles"
OUT_HTML = "Sentinel2_offline.html"
WORKERS = 16


def lon2tilex(lon, z):
    return int((lon + 180.0) / 360.0 * (2 ** z))


def lat2tiley(lat, z):
    r = math.radians(lat)
    return int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (2 ** z))


def build_composite(project):
    ee.Initialize(project=project)
    print(f"[ok] EE initialized ({project})")

    thailand = (
        ee.FeatureCollection("FAO/GAUL/2015/level0")
        .filter(ee.Filter.eq("ADM0_NAME", "Thailand"))
    )
    aoi = thailand.geometry()

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(START_DATE, END_DATE)
    )
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    s2 = s2.linkCollection(cs, ["cs"])
    s2 = s2.map(lambda i: i.updateMask(i.select("cs").gte(CS_THRESHOLD)))

    composite = s2.select(["B4", "B3", "B2"]).median().clip(aoi)
    print("[ok] cloud-free median composite ready")

    bounds = aoi.bounds().coordinates().getInfo()[0]
    xs = [c[0] for c in bounds]
    ys = [c[1] for c in bounds]
    bbox = (min(xs), min(ys), max(xs), max(ys))  # (w, s, e, n)
    print(f"[info] Thailand bbox: {bbox}")
    return composite, bbox


def tile_list(bbox, zmin, zmax):
    w, s, e, n = bbox
    tiles = []
    for z in range(zmin, zmax + 1):
        x0, x1 = lon2tilex(w, z), lon2tilex(e, z)
        y0, y1 = lat2tiley(n, z), lat2tiley(s, z)  # n->small y, s->large y
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                tiles.append((z, x, y))
    return tiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--zmin", type=int, default=0)
    ap.add_argument("--zmax", type=int, default=11)
    args = ap.parse_args()

    composite, bbox = build_composite(args.project)

    url_tmpl = composite.getMapId(VIS)["tile_fetcher"].url_format
    print("[ok] EE tile URL acquired (token valid during download)")

    tiles = tile_list(bbox, args.zmin, args.zmax)
    total = len(tiles)
    print(f"[info] tiles to fetch (z{args.zmin}-{args.zmax}): {total}")

    session = requests.Session()
    saved = {"ok": 0, "empty": 0, "fail": 0}

    def fetch(zxy):
        z, x, y = zxy
        out = os.path.join(TILE_DIR, str(z), str(x), f"{y}.png")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return "ok"     # resume: ข้ามไฟล์ที่ดาวน์โหลดแล้ว
        url = url_tmpl.format(z=z, x=x, y=y)
        try:
            r = session.get(url, timeout=60)
        except Exception:
            return "fail"
        if r.status_code == 200 and r.content:
            path = os.path.join(TILE_DIR, str(z), str(x))
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, f"{y}.png"), "wb") as f:
                f.write(r.content)
            return "ok"
        if r.status_code in (400, 404):
            return "empty"      # นอกขอบเขตภาพ / ไม่มีข้อมูล
        return "fail"

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch, t): t for t in tiles}
        for fut in as_completed(futs):
            saved[fut.result()] += 1
            done += 1
            if done % 250 == 0 or done == total:
                print(f"  {done}/{total}  ok={saved['ok']} empty={saved['empty']} fail={saved['fail']}")

    print(f"[done] tiles saved: {saved['ok']}  (empty={saved['empty']}, fail={saved['fail']})")
    write_html(bbox, args.zmax)
    print(f"[done] wrote {OUT_HTML}")


def write_html(bbox, zmax):
    w, s, e, n = bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sentinel-2 Thailand 2026 (offline tiles)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body{{height:100%;margin:0}}
  #map{{position:absolute;inset:0}}
  .info-box{{position:absolute;top:12px;left:52px;z-index:1000;
    background:rgba(255,255,255,.92);padding:8px 12px;border-radius:8px;
    font:600 14px/1.3 "Segoe UI",Tahoma,sans-serif;color:#222;
    box-shadow:0 1px 6px rgba(0,0,0,.3)}}
</style>
</head>
<body>
<div id="map"></div>
<div class="info-box">Sentinel-2 &mdash; ประเทศไทย 2026 (cloud-free · offline tiles)</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map').setView([{cy:.4f}, {cx:.4f}], 6);

const gsat = L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}',
  {{maxZoom:21, attribution:'Google Satellite'}}).addTo(map);

const s2 = L.tileLayer('./{TILE_DIR}/{{z}}/{{x}}/{{y}}.png',
  {{maxNativeZoom:{zmax}, maxZoom:19, opacity:1.0,
    bounds:[[{s:.4f},{w:.4f}],[{n:.4f},{e:.4f}]],
    attribution:'Google Earth Engine | Copernicus Sentinel-2'}}).addTo(map);

L.control.layers(
  {{'Google Satellite': gsat}},
  {{'Sentinel-2 median 2026': s2}},
  {{collapsed:false}}
).addTo(map);
</script>
</body>
</html>
"""
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
