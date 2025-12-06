# backend/db.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:1234567@localhost:5432/air_quality"
)

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
