"""Offline benchmark: python -m backend.tests.benchmark_dealer_summary.

Cold clears only the parsed CSV cache, not OS file caches or interpreter state.
Warm primes that cache once. No result/balance cache, provider, or socket is used.
"""
import os
os.environ["USE_SAMPLE_DATA"] = "true"

import json
from statistics import median
from time import perf_counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.api.commission_routes import router
from backend.db import queries
from backend.db.connection import execute_query


def measure(call, cold, repeats=7):
    call()
    timings = []
    for _ in range(repeats):
        if cold:
            queries._clear_csv_cache()
        start = perf_counter()
        call()
        timings.append((perf_counter() - start) * 1000)
    return {"median_ms": round(median(timings), 2),
            "min_ms": round(min(timings), 2), "max_ms": round(max(timings), 2),
            "runs": repeats}


def main():
    # dotenv may override the environment during config import. This standalone
    # offline benchmark must never dispatch through the live data path.
    config.USE_SAMPLE_DATA = True
    assert config.USE_SAMPLE_DATA is True
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        def api():
            response = client.get('/commissions?mon_period=202603&prior_period=202602')
            response.raise_for_status()
            return response.json()

        workloads = {
            "march_summary": lambda: execute_query("get_dealer_summary", {"mon_period": "202603"}),
            "march_api_with_feb_comparison": api,
        }
        results = {name: {state: measure(call, cold) for state, cold in
                         [("warm", False), ("cold_csv", True)]}
                   for name, call in workloads.items()}
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
