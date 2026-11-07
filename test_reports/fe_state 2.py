"""Set up / tear down insurance flag states for frontend testing.
usage: python fe_state.py setup|teardown
"""
import os, sys
from datetime import datetime, timedelta, timezone
import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"


def login(e, p):
    d = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30).json()
    return d["access_token"], d["user"]["id"]


atok, _ = login("gabrielosmanhamza@yahoo.com", "Admin@123")
h = {"Authorization": f"Bearer {atok}"}
_, d1 = login("driver1@test.com", "Driver@123")
_, nd = login("newdriver@test.com", "NewDriver@123")

mode = sys.argv[1]
if mode == "setup":
    print("d1 expired:", requests.put(f"{API}/drivers/{d1}/record", json={"insurance_expiry": "2025-01-01"}, headers=h, timeout=30).status_code)
    soon = (datetime.now(timezone.utc).date() + timedelta(days=15)).isoformat()
    print("nd soon:", requests.put(f"{API}/drivers/{nd}/record", json={"insurance_expiry": soon}, headers=h, timeout=30).status_code)
else:
    future = (datetime.now(timezone.utc).date() + timedelta(days=365)).isoformat()
    print("d1 restore:", requests.put(f"{API}/drivers/{d1}/record", json={"insurance_expiry": future, "verification_status": "approved"}, headers=h, timeout=30).status_code)
    print("nd restore:", requests.put(f"{API}/drivers/{nd}/record", json={"insurance_expiry": future, "verification_status": "incomplete"}, headers=h, timeout=30).status_code)

recs = requests.get(f"{API}/admin/driver-verifications", headers=h, timeout=30).json()["drivers"]
for r in recs:
    print(r["email"], r["verification_status"], r["insurance_expiry"], r["insurance_flag"], r["compliant"], r["user_id"])
