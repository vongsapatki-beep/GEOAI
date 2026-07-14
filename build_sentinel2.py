"""
Build Sentinel2.html  (pure folium + Earth Engine tile URLs)
- ขอบเขต: ประเทศไทย (FAO/GAUL/2015/level0)
- ช่วงเวลา: 2026-01-01 ถึงปัจจุบัน (2026-07-14)
- Cloud-free median composite (Cloud Score+ masking)
- พื้นหลัง: Google Satellite

Usage:
    .venv/Scripts/python.exe build_sentinel2.py --project <GCP_PROJECT_ID>

หมายเหตุ: EE tile URL มี token ที่หมดอายุในไม่กี่ชม.-วัน
ถ้าเลเยอร์ S2 หาย ให้รันสคริปต์นี้ใหม่เพื่อสร้าง token ใหม่
"""
import argparse
import ee
import folium

START_DATE = "2026-01-01"
END_DATE = "2026-07-14"           # ปี 2026 เท่าที่มีข้อมูล
CS_THRESHOLD = 0.60               # Cloud Score+ : เก็บ pixel ที่ cs >= 0.60
OUT_HTML = "Sentinel2.html"
VIS = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.1}


def ee_tile_url(ee_image, vis):
    """Return an XYZ tile URL template for an EE image."""
    mapid = ee_image.getMapId(vis)
    return mapid["tile_fetcher"].url_format


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Google Cloud project ID (EE enabled)")
    args = ap.parse_args()

    ee.Initialize(project=args.project)
    print(f"[ok] Earth Engine initialized with project '{args.project}'")

    # ---------- AOI: Thailand ----------
    thailand = (
        ee.FeatureCollection("FAO/GAUL/2015/level0")
        .filter(ee.Filter.eq("ADM0_NAME", "Thailand"))
    )
    aoi = thailand.geometry()
    print("[ok] AOI = Thailand (FAO GAUL level0)")

    # ---------- Sentinel-2 SR + Cloud Score+ ----------
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(START_DATE, END_DATE)
    )
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    s2 = s2.linkCollection(cs, ["cs"])

    def mask_clouds(img):
        return img.updateMask(img.select("cs").gte(CS_THRESHOLD))

    count = s2.size().getInfo()
    print(f"[info] Sentinel-2 scenes in range: {count}")

    composite = (
        s2.map(mask_clouds)
        .select(["B4", "B3", "B2"])
        .median()
        .clip(aoi)
    )
    print("[ok] Cloud-free median composite built")

    # boundary outline as an EE image (yellow, ~2px)
    outline = ee.Image().byte().paint(featureCollection=thailand, color=1, width=2)

    # ---------- tile URLs ----------
    print("[info] requesting EE tile URLs ...")
    s2_url = ee_tile_url(composite, VIS)
    line_url = ee_tile_url(outline, {"palette": ["FFFF00"]})
    print("[ok] tile URLs ready")

    # ---------- folium map ----------
    # center of Thailand approx
    m = folium.Map(location=[13.5, 100.9], zoom_start=6, tiles=None, control_scale=True)

    # Base: Google Satellite
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        name="Google Satellite",
        max_zoom=21,
        overlay=False,
        control=True,
    ).add_to(m)

    # Sentinel-2 cloud-free median
    folium.TileLayer(
        tiles=s2_url,
        attr="Google Earth Engine | Copernicus Sentinel-2",
        name="Sentinel-2 median 2026 (cloud-free)",
        overlay=True,
        control=True,
    ).add_to(m)

    # Thailand boundary
    folium.TileLayer(
        tiles=line_url,
        attr="FAO GAUL",
        name="Thailand boundary",
        overlay=True,
        control=True,
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # title box
    title = (
        '<div style="position:fixed;top:12px;left:52px;z-index:9999;'
        'background:rgba(255,255,255,.92);padding:8px 12px;border-radius:8px;'
        'font:600 14px/1.3 \'Segoe UI\',Tahoma,sans-serif;color:#222;'
        'box-shadow:0 1px 6px rgba(0,0,0,.3)">'
        'Sentinel-2 &mdash; ประเทศไทย 2026 '
        '(cloud-free median)</div>'
    )
    m.get_root().html.add_child(folium.Element(title))

    m.save(OUT_HTML)
    print(f"[done] wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
