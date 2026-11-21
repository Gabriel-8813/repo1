"""Probe: repeated concurrent accept races (demo.driver vs driver1) — must never yield two 200s."""
import sys, threading
sys.path.insert(0, "/app/backend/tests")
import requests
from test_launch_hardening import API, CREDS, DB

tok = {}
for role in ("driver", "driver2", "facility", "dispatcher"):
    e, p = CREDS[role]
    tok[role] = requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["access_token"]
H = lambda r: {"Authorization": f"Bearer {tok[r]}"}
for i in range(6):
    j = requests.post(f"{API}/facility/requests", headers=H("facility"), json={
        "recipient_name": "TEST_Race", "recipient_phone": "+14165550199", "dropoff_address": "100 Queen St W, Toronto, ON",
        "item_count": 1, "item_category": "prescription", "handling_flags": [], "requested_pickup_time": "2026-02-01T10:00",
        "consent_data_handling": True}).json()
    jid = j["id"]
    res = {}
    b = threading.Barrier(2)
    def go(r):
        b.wait()
        res[r] = requests.post(f"{API}/jobs/{jid}/accept", headers=H(r)).status_code
    ts = [threading.Thread(target=go, args=(r,)) for r in ("driver", "driver2")]
    [t.start() for t in ts]; [t.join() for t in ts]
    doc = DB.jobs.find_one({"id": jid})
    print(i, res, "winner", doc["accepted_by"][:8])
    requests.put(f"{API}/jobs/{jid}", json={"status": "cancelled"}, headers=H("dispatcher"))
