# backend/etl.py
import os
import requests
from datetime import datetime
from .db import get_conn

WAQI_TOKEN = "0c03d697abda52942e8bf069cb285d7669d576f4"
# Danh sách ID trạm, bạn có thể bổ sung thêm sau
HANOI_STATIONS = [
    # 1583,   # Hanoi, Vietnam
    8688,   # UNIS
    13026,  # Chi cục BVMT
    # 8641,   # US Embassy
    # 13427,  # TT giao lưu VH phố cổ
    # 13431,  # Tứ Hiệp - Thanh Trì
    # 13419,  # Cung thiếu nhi
    # 13685,  # Láng Thượng
    # 13686,  # Hồng Hà

]  # ID kiểu @1583

BASE_URL = "https://api.waqi.info/feed/@{id}/?token={token}"

def fetch_station_data(station_id: int):
    url = BASE_URL.format(id=station_id, token=WAQI_TOKEN)
    r = requests.get(url, timeout=10)
    data = r.json()
    if data.get("status") != "ok":
        print("Station", station_id, "status not ok:", data)
        return None

    d = data["data"]
    iaqi = d.get("iaqi", {})

    def v(key):
        val = iaqi.get(key)
        if isinstance(val, dict):
            return val.get("v")
        return None

    city = d.get("city", {})
    geo = city.get("geo", [None, None])  # [lat, lon]
    lat = float(geo[0]) if geo[0] is not None else None
    lon = float(geo[1]) if geo[1] is not None else None
    if lat is None or lon is None:
        print(f"Station {station_id} missing coordinates, skip")
        return None

    name = city.get("name", f"Station {station_id}")

    aqi = d.get("aqi")
    try:
        aqi = int(aqi)
    except Exception:
        aqi = None

    # ---- SỬA PHẦN TIME Ở ĐÂY ----
    time_info = d.get("time", {})
    ts_raw = time_info.get("s") or time_info.get("stime")
    if not ts_raw:
        print(f"Station {station_id} missing time.s/stime, skip")
        return None

    try:
        ts = datetime.fromisoformat(ts_raw.replace(" ", "T"))
    except Exception as e:
        print(f"Cannot parse time '{ts_raw}' for station {station_id}, skip:", e)
        return None
    # ------------------------------

    return {
        "source": "waqi",
        "source_station_id": f"{station_id}",
        "name": name,
        "lon": lon,
        "lat": lat,
        "ts_utc": ts,
        "aqi": aqi,
        "pm25": v("pm25"),
        "pm10": v("pm10"),
        "o3": v("o3"),
        "no2": v("no2"),
        "co": v("co"),
        "temperature": v("t"),
        "humidity": v("h"),
            "pressure": v("p"),
    "wind": v("w"),
    "dew_point": v("dew"),
        "raw_json": d,
    }


def upsert_station(cur, s):
    cur.execute(
        """
        INSERT INTO stations (source, source_station_id, name, lon, lat)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (source_station_id)
        DO UPDATE SET name = EXCLUDED.name, lon = EXCLUDED.lon, lat = EXCLUDED.lat
        RETURNING id;
        """,
        (s["source"], s["source_station_id"], s["name"], s["lon"], s["lat"])
    )
    row = cur.fetchone()
    return row["id"]

def insert_measurement(cur, station_db_id, s):
    cur.execute(
        """
        INSERT INTO measurements (
            station_id, ts_utc, aqi, pm25, pm10, o3, no2, co,
            temperature, humidity, pressure, wind, dew_point, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, ts_utc) DO NOTHING;
        """,
        (
            station_db_id, s["ts_utc"], s["aqi"], s["pm25"], s["pm10"],
            s["o3"], s["no2"], s["co"],
            s["temperature"], s["humidity"], s["pressure"], s["wind"], s["dew_point"],
            json.dumps(s["raw_json"])
        )
    )

import json

def run_once():
    conn = get_conn()
    cur = conn.cursor()
    try:
        for sid in HANOI_STATIONS:
            sdata = fetch_station_data(sid)
            if not sdata:
                continue
            station_db_id = upsert_station(cur, sdata)
            insert_measurement(cur, station_db_id, sdata)
            print("Inserted data for station", sdata["name"], "at", sdata["ts_utc"])
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error:", e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_once()
