# backend/app.py
import os
import json
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .db import get_conn

app = FastAPI(title="Hanoi Air Quality GIS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def row_to_feature(row):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [row["lon"], row["lat"]],
        },
        "properties": {
            "station_id": row["station_id"],
            "name": row["name"],
            "aqi": row["aqi"],
            "pm25": row["pm25"],
            "pm10": row["pm10"],
            "ts_utc": row["ts_utc"].isoformat() if row["ts_utc"] else None,
        },
    }

@app.get("/api/stations")
def get_stations():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, lon, lat FROM stations ORDER BY id;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@app.get("/api/latest")
def get_latest():
    """
    Lấy đo mới nhất cho mỗi trạm, trả về GeoJSON
    """
    sql = """
    SELECT s.id AS station_id, s.name, s.lon, s.lat,
           m.aqi, m.pm25, m.pm10, m.ts_utc
    FROM stations s
    JOIN LATERAL (
        SELECT *
        FROM measurements m
        WHERE m.station_id = s.id
        ORDER BY m.ts_utc DESC
        LIMIT 1
    ) m ON TRUE;
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = [row_to_feature(r) for r in rows]
    return {
        "type": "FeatureCollection",
        "features": features,
    }

@app.get("/api/history")
def get_history(
    station_id: int,
    hours: int = Query(24, ge=1, le=720)
):
    """
    Lịch sử AQI/PM cho 1 trạm (tạm thời bỏ filter theo giờ để tránh lệch timezone).
    """
    sql = """
    SELECT ts_utc, aqi, pm25, pm10
    FROM measurements
    WHERE station_id = %s
    ORDER BY ts_utc ASC;
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, (station_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

@app.get("/api/district_aqi")
def district_aqi():
    """
    AQI trung bình theo quận, tính từ:
    - các trạm WAQI (measurements + stations)
    - các city-level IQAir (iqair_observation + iqair_station)
    """
    sql = """
    -- Lần đo mới nhất của mỗi trạm WAQI, kèm quận chứa trạm
    WITH latest_waqi AS (
        SELECT 
            d.id AS district_id,
            m.aqi         AS aqi
        FROM stations s
        JOIN LATERAL (
            SELECT aqi, ts_utc
            FROM measurements m
            WHERE m.station_id = s.id
            ORDER BY ts_utc DESC
            LIMIT 1
        ) m ON TRUE
        JOIN hanoi_district d
          ON ST_Contains(
                d.geom,
                ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326)
             )
    ),

    -- Lần đo mới nhất của mỗi trạm IQAir (city-level), đã biết district_id
    latest_iqair AS (
        SELECT 
            s.district_id,
            o.aqi_us      AS aqi
        FROM iqair_station s
        JOIN LATERAL (
            SELECT aqi_us, ts
            FROM iqair_observation o
            WHERE o.station_id = s.id
            ORDER BY ts DESC
            LIMIT 1
        ) o ON TRUE
        WHERE s.is_active = TRUE
          AND s.district_id IS NOT NULL
    ),

    -- Gộp tất cả lại, mỗi dòng = 1 giá trị AQI của 1 trạm thuộc 1 quận
    latest_all AS (
        SELECT * FROM latest_waqi
        UNION ALL
        SELECT * FROM latest_iqair
    )

    SELECT 
        d.id,
        d.name,
        AVG(latest_all.aqi)::int AS aqi_avg,
        ST_AsGeoJSON(d.geom)::json AS geom_geojson
    FROM hanoi_district d
    LEFT JOIN latest_all
      ON latest_all.district_id = d.id
    GROUP BY d.id, d.name, d.geom
    ORDER BY d.name;
    """

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": r["geom_geojson"],
            "properties": {
                "id":      r["id"],
                "name":    r["name"],
                "aqi_avg": r["aqi_avg"],
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@app.get("/api/city_trend")
def city_trend(hours: int = 24):
    """
    Trả về AQI trung bình toàn thành phố theo từng giờ trong N giờ gần nhất.
    Dùng cho biểu đồ xu hướng.
    """
    # Giới hạn giờ cho an toàn
    if hours < 1:
        hours = 1
    if hours > 24 * 14:  # tối đa 14 ngày
        hours = 24 * 14

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    sql = """
        SELECT 
            date_trunc('hour', ts_utc) AS hour,
            AVG(aqi)::int  AS aqi_avg,
            AVG(pm25)      AS pm25_avg
        FROM measurements
        WHERE ts_utc BETWEEN %s AND %s
        GROUP BY date_trunc('hour', ts_utc)
        ORDER BY hour;
    """

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, (start_time, end_time))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "hour": r["hour"],
            "aqi_avg": r["aqi_avg"],
            "pm25_avg": float(r["pm25_avg"]) if r["pm25_avg"] is not None else None
        })

    return result


# iqair
def iqair_row_to_feature(row):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [row["lon"], row["lat"]],
        },
        "properties": {
            "station_id": row["station_id"],
            "city": row["city"],
            "display_name": row["display_name"],
            "aqi_us": row["aqi_us"],
            "ts": row["ts"].isoformat() if row["ts"] else None,
        },
    }

@app.get("/api/iqair_points")
def get_iqair_points():
    sql = """
    SELECT 
        s.id AS station_id,
        s.city,
        s.display_name,
        ST_X(s.geom) AS lon,
        ST_Y(s.geom) AS lat,
        o.aqi_us,
        o.ts
    FROM iqair_station s
    JOIN LATERAL (
        SELECT *
        FROM iqair_observation o
        WHERE o.station_id = s.id
        ORDER BY o.ts DESC
        LIMIT 1
    ) o ON TRUE
    WHERE s.is_active = TRUE;
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    features = [iqair_row_to_feature(r) for r in rows]
    return {"type": "FeatureCollection", "features": features}

@app.get("/api/station_detail")
def station_detail(
    source: str = Query(..., regex="^(waqi|iqair)$"),
    station_id: int = Query(...)
):
    """
    Trả về thông tin chi tiết trạm (mới nhất)
    - WAQI: từ stations + measurements
    - IQAir: từ iqair_station + iqair_observation
    """
    conn = get_conn()
    cur = conn.cursor()

    try:
        # ===========================
        # 1) TRẠM WAQI (stations + measurements)
        # ===========================
        if source == "waqi":
            cur.execute("""
                SELECT
                    s.id AS station_id,
                    s.name,
                    s.lon,
                    s.lat,
                    m.ts_utc,
                    m.aqi,
                    m.pm25,
                    m.pm10,
                    m.o3,
                    m.no2,
                    m.co,
                    m.temperature,
                    m.humidity,
                    m.pressure,
                    m.wind,
                    m.dew_point
                FROM stations s
                JOIN measurements m
                    ON s.id = m.station_id
                WHERE s.id = %s
                ORDER BY m.ts_utc DESC
                LIMIT 1
            """, (station_id,))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu trạm WAQI")

            return row

        # ===========================
        # 2) TRẠM IQAIR (iqair_station + iqair_observation)
        # ===========================
        else:  # source == "iqair"
            cur.execute("""
                SELECT
                    s.id AS station_id,
                    s.display_name,
                    s.city,
                    s.state,
                    s.country,
                    ST_AsGeoJSON(s.geom) AS geom,
                    o.ts AS ts_local,
                    o.aqi_us,
                    o.main_us,
                    o.aqi_cn,
                    o.main_cn,
                    o.humidity,
                    o.temperature AS temp,
                    o.pressure,
                    o.wind_speed,
                    o.wind_dir,
                    o.heat_index,
                    o.weather_icon
                FROM iqair_station s
                JOIN iqair_observation o
                    ON s.id = o.station_id
                WHERE s.id = %s
                ORDER BY o.ts DESC
                LIMIT 1
            """, (station_id,))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu trạm IQAir")

            return row
    finally:
        cur.close()
        conn.close()

