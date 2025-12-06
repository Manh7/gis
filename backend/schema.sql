CREATE EXTENSION IF NOT EXISTS postgis;

-- Bảng trạm đo
CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    source VARCHAR(16) NOT NULL,
    source_station_id VARCHAR(64) NOT NULL UNIQUE,
    name TEXT,
    lon DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    geom GEOGRAPHY(POINT, 4326) GENERATED ALWAYS AS (
        ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    ) STORED
);

-- Bảng measurements (dữ liệu theo thời gian)
CREATE TABLE IF NOT EXISTS measurements (
    id BIGSERIAL PRIMARY KEY,
    station_id INT REFERENCES stations(id) ON DELETE CASCADE,
    ts_utc TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    aqi INT,
    pm25 REAL,
    pm10 REAL,
    o3 REAL,
    no2 REAL,
    so2 REAL,
    co REAL,
    temperature REAL,
    humidity REAL,
    raw_json JSONB,
    UNIQUE (station_id, ts_utc)
);

-- Optional: ranh giới hành chính Hà Nội (quận/huyện) nếu có shapefile
-- CREATE TABLE hanoi_district (..., geom GEOGRAPHY(POLYGON, 4326));
