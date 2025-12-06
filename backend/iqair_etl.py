# backend/iqair_etl.py
import os
import time
import requests
from datetime import datetime
from .db import get_conn  # dùng chung hàm kết nối :contentReference[oaicite:3]{index=3}

IQAIR_KEY = "9be8835d-aa22-4aa0-a46c-f0eba351848f" # để trong .env
BASE_CITY_URL = "https://api.airvisual.com/v2/city"

# 8 city-level bạn muốn dùng
HANOI_CITIES = [
    "Thach That",
    "Trau Quy", #Gia Lâm
    "Phường Phú Thượng", #Tây Hồ
    "Hanoi", #Ba Đình
    "Hoan Kiem",
    "Thanh Xuan",
    "Tay Ho",
    "Hai BaTrung",
]

def fetch_city(city: str):
    params = {
        "city": city,
        "state": "Hanoi",
        "country": "Vietnam",
        "key": IQAIR_KEY,
    }
    r = requests.get(BASE_CITY_URL, params=params, timeout=10)
    data = r.json()
    if data.get("status") != "success":
        print("IQAir city", city, "status not success:", data)
        return None

    d = data["data"]
    loc = d["location"]["coordinates"]   # [lon, lat]
    lon, lat = float(loc[0]), float(loc[1])

    pol = d["current"]["pollution"]
    w   = d["current"]["weather"]

    ts = datetime.fromisoformat(pol["ts"].replace("Z", "+00:00"))

    return {
        "city": d["city"],
        "state": d["state"],
        "country": d["country"],
        "display_name": d["city"],  # có thể custom sau
        "lon": lon,
        "lat": lat,
        "ts": ts,
        "aqius": pol["aqius"],
        "mainus": pol["mainus"],
        "aqicn": pol["aqicn"],
        "maincn": pol["maincn"],
        "weather": {
            "icon": w["ic"],
            "hu": w["hu"],
            "pr": w["pr"],
            "tp": w["tp"],
            "wd": w["wd"],
            "ws": w["ws"],
            "heatIndex": w.get("heatIndex"),
        }
    }

def upsert_iqair_station(cur, s):
    cur.execute(
        """
        INSERT INTO iqair_station (city, state, country, display_name, geom)
        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ON CONFLICT (city, state, country)
        DO UPDATE SET
          display_name = EXCLUDED.display_name,
          geom = EXCLUDED.geom
        RETURNING id;
        """,
        (s["city"], s["state"], s["country"], s["display_name"], s["lon"], s["lat"])
    )
    row = cur.fetchone()
    station_id = row["id"]

    # Gán district nếu chưa có
    cur.execute(
        """
        UPDATE iqair_station st
        SET district_id = d.id
        FROM hanoi_district d
        WHERE st.id = %s
          AND st.district_id IS NULL
          AND ST_Contains(d.geom, st.geom);
        """,
        (station_id,)
    )

    return station_id

def insert_iqair_observation(cur, station_id, s):
    w = s["weather"]
    cur.execute(
        """
        INSERT INTO iqair_observation (
            station_id, ts,
            aqi_us, main_us, aqi_cn, main_cn,
            weather_icon, humidity, pressure, temperature,
            wind_dir, wind_speed, heat_index
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, ts) DO NOTHING;
        """,
        (
            station_id, s["ts"],
            s["aqius"], s["mainus"],
            s["aqicn"], s["maincn"],
            w["icon"], w["hu"], w["pr"], w["tp"],
            w["wd"], w["ws"], w["heatIndex"],
        )
    )

def run_iqair_once():
    conn = get_conn()
    cur = conn.cursor()
    try:
        for city in HANOI_CITIES:
            s = fetch_city(city)
            if not s:
                continue
            sid = upsert_iqair_station(cur, s)
            insert_iqair_observation(cur, sid, s)
            print("IQAir:", city, "at", s["ts"])
            conn.commit()
            time.sleep(30)  # nghỉ 7s để tránh Too Many Requests
    except Exception as e:
        conn.rollback()
        print("IQAir error:", e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_iqair_once()
