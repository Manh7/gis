# backend/worker.py
from time import sleep
from .etl import run_once
from .iqair_etl import run_iqair_once

if __name__ == "__main__":
    print("Air quality worker started. Fetching data every 30 minutes...")
    while True:
        run_once()
        run_iqair_once()
        # Nghỉ 30 phút (1800 giây)
        sleep(1800)
