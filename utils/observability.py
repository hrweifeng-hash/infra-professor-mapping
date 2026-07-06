import time
from datetime import datetime


def _now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def stage_start(name: str):
    start = time.time()
    print(f"[STAGE START] {name} | start={_now_iso()}", flush=True)
    return start


def stage_end(name: str, start: float):
    end = time.time()
    elapsed = end - start
    print(f"[STAGE END]   {name} | end={_now_iso()} | elapsed={elapsed:.3f}s", flush=True)


def progress(name: str, count: int, interval: int = 100000):
    if count % interval == 0:
        print(f"[PROGRESS] {name} | processed={count}", flush=True)
