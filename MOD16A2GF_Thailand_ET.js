/**************************************************************
 * วิเคราะห์ค่า Evapotranspiration (ET) ของประเทศไทย
 * ข้อมูล: MODIS MOD16A2GF (Collection 6.1)
 * ช่วงเวลา: 2023-01-01 ถึง 2023-12-31
 * รันได้ทันทีใน Google Earth Engine Code Editor
 **************************************************************/

/* ============================================================
 * ข้อ 1) โหลด dataset MOD16A2GF เลือก band 'ET'
 *        และกำหนดช่วงวันที่ปี 2023
 * ============================================================ */
var startDate = '2023-01-01';
var endDate   = '2023-12-31';

var modisET = ee.ImageCollection('MODIS/061/MOD16A2GF')
                .select('ET')
                .filterDate(startDate, endDate);

/* ============================================================
 * ข้อ 2) ขอบเขตประเทศไทยจาก LSIB (filter country_na = 'Thailand')
 * ============================================================ */
var thailand = ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
                 .filter(ee.Filter.eq('country_na', 'Thailand'));

/* ============================================================
 * ข้อ 3) *** จุดแก้ projection จุดที่ 1 ***
 *        Simplify geometry ด้วย maxError 1000 เมตร
 *        เพื่อลดจำนวน vertex ของขอบเขต ป้องกัน
 *        projection / geodesic error ตอน reduceRegion
 * ============================================================ */
var geometry = thailand.geometry().simplify({ maxError: 1000 });

/* ============================================================
 * ข้อ 4) ฟังก์ชัน clean ข้อมูล ET
 *        - mask ค่า > 32700 (fill values) ออก
 *        - คูณ scale factor 0.1 => mm/8day
 *        - copyProperties 'system:time_start' กลับมาด้วย
 * ============================================================ */
function cleanET(image) {
  // mask ค่าเกิน 32700 ซึ่งเป็น fill value ออก
  var masked = image.updateMask(image.lte(32700));
  // คูณ scale factor 0.1 เพื่อแปลงหน่วยเป็น mm/8day
  var scaled = masked.multiply(0.1);
  // คืนค่า property 'system:time_start' กลับมาเพื่อใช้ทำ time series ต่อ
  return scaled.copyProperties(image, ['system:time_start']);
}

var etCleaned = modisET.map(cleanET);

/* ============================================================
 * ข้อ 5) คำนวณ ET สะสมรายปี (sum ทั้ง collection)
 *        แล้ว clip ด้วย geometry ที่ simplify แล้ว
 * ============================================================ */
var etAnnual = etCleaned.sum().clip(geometry);

/* ============================================================
 * ข้อ 6) กำหนดจุดศูนย์กลางแผนที่ที่ประเทศไทย zoom 6
 * ============================================================ */
Map.centerObject(geometry, 6);

/* ============================================================
 * ข้อ 7) แสดง layer ET สะสมรายปี
 *        palette โทน YlGnBu 7 สี (เหลือง-เขียว-ฟ้า-น้ำเงินเข้ม)
 *        ช่วง min 0, max 1500
 * ============================================================ */
var etVis = {
  min: 0,
  max: 1500,
  palette: [
    '#ffffcc', // เหลืองอ่อน
    '#c7e9b4',
    '#7fcdbb',
    '#41b6c4',
    '#1d91c0',
    '#225ea8',
    '#0c2c84'  // น้ำเงินเข้ม
  ]
};
Map.addLayer(etAnnual, etVis, 'ET สะสมรายปี 2566 (mm/ปี)');

/* ============================================================
 * ข้อ 8) แสดงขอบเขตประเทศไทยเป็นเส้นสีแดง ไม่มี fill
 *        ใช้ .style (fillColor โปร่งใส '00000000')
 * ============================================================ */
var thailandOutline = thailand.style({
  color: 'red',
  fillColor: '00000000', // โปร่งใส ไม่มี fill
  width: 2
});
Map.addLayer(thailandOutline, {}, 'ขอบเขตประเทศไทย');

/* ============================================================
 * ข้อ 9) กราฟ Time Series
 *        *** ห้ามใช้ ui.Chart.image.series ***
 *        เพราะจะเจอ projection error กับ MODIS sinusoidal
 *        วิธีแก้: map ทั้ง collection แล้ว reduceRegion เอง
 * ============================================================ */
var etTimeSeries = etCleaned.map(function(image) {
  // *** จุดแก้ projection จุดที่ 2 ***
  // บังคับ crs 'EPSG:4326' ตอน reduceRegion
  // เพื่อเลี่ยงการคำนวณบน sinusoidal projection ของ MODIS
  var meanDict = image.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: geometry,
    crs: 'EPSG:4326',   // <-- บังคับ CRS เป็น lat/lon
    scale: 5000,
    maxPixels: 1e13,
    bestEffort: true
  });

  // แปลง system:time_start เป็นข้อความวันที่ (YYYY-MM-dd)
  var dateStr = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd');

  // สร้าง feature เก็บวันที่และค่า ET เฉลี่ย
  return ee.Feature(null, {
    'date': dateStr,
    'ET': meanDict.get('ET')
  });
});

var etTimeSeriesFC = ee.FeatureCollection(etTimeSeries);

/* ============================================================
 * ข้อ 10) filter feature ที่ ET เป็น null ออก
 * ============================================================ */
var etTimeSeriesClean = etTimeSeriesFC.filter(ee.Filter.notNull(['ET']));

/* ============================================================
 * ข้อ 11) plot กราฟด้วย ui.Chart.feature.byFeature (LineChart)
 *         แกน x = วันที่ (เอียง 45 องศา), แกน y = ET (mm/8day)
 *         มีทั้ง point และ line
 * ============================================================ */
var etChart = ui.Chart.feature.byFeature({
  features: etTimeSeriesClean,
  xProperty: 'date',
  yProperties: ['ET']
})
.setChartType('LineChart')
.setOptions({
  title: 'ค่า Evapotranspiration (ET) เฉลี่ยรายภาพ ประเทศไทย ปี 2566',
  hAxis: {
    title: 'วันที่',
    slantedText: true,
    slantedTextAngle: 45
  },
  vAxis: {
    title: 'ET (mm/8day)'
  },
  lineWidth: 2,
  pointSize: 4,       // แสดงจุด (point)
  colors: ['#225ea8']
});
print(etChart);

/* ============================================================
 * ข้อ 12) print ค่า ET สะสมเฉลี่ยทั้งประเทศรายปี
 *         reduceRegion แบบเดียวกัน (บังคับ EPSG:4326)
 * ============================================================ */
var etAnnualMean = etAnnual.reduceRegion({
  reducer: ee.Reducer.mean(),
  geometry: geometry,
  crs: 'EPSG:4326',   // <-- จุดแก้ projection: บังคับ CRS เช่นเดียวกับข้อ 9
  scale: 5000,
  maxPixels: 1e13,
  bestEffort: true
});

print('ET สะสมเฉลี่ยทั้งประเทศ ปี 2566 (mm/ปี):', etAnnualMean.get('ET'));
