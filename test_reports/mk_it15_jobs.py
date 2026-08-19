import json
import sys
import requests
from dotenv import dotenv_values

API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def tok(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d.get("access_token") or d.get("token"), d.get("user", {})


dt, _ = tok("dispatcher1@test.com", "Dispatch@123")
at, _ = tok("gabrielosmanhamza@yahoo.com", "Admin@123")
dh = {"Authorization": f"Bearer {dt}"}
ah = {"Authorization": f"Bearer {at}"}

cmd = sys.argv[1]

if cmd == "create":
    ids = []
    for i in range(3):
        p = {
            "title": f"TEST_UI15 Job {i+1}",
            "description": "iteration15 UI job",
            "pickup_address": "455 Queen St W, Toronto, ON",
            "dropoff_address": "100 Queen St W, Toronto, ON",
            "item_category": "lab_sample",
            "recipient_name": "QA Lab",
            "recipient_phone": "416-555-0111",
            "payout_amount": 33.0,
            "distance_km": 3.0,
            "handling_flags": ["urgent"] if i == 2 else [],
        }
        r = requests.post(f"{API}/jobs", json=p, headers=dh, timeout=60)
        r.raise_for_status()
        ids.append(r.json()["id"])
    print(json.dumps(ids))
elif cmd == "status":
    jid, st = sys.argv[2], sys.argv[3]
    dr, du = tok("driver1@test.com", "Driver@123")
    body = {"status": st}
    if st in ("offered", "accepted"):
        body["assigned_driver_id"] = du["id"]
    r = requests.put(f"{API}/jobs/{jid}", json=body, headers=dh, timeout=30)
    print(r.status_code, r.text[:200])
elif cmd == "get":
    r = requests.get(f"{API}/jobs/{sys.argv[2]}", headers=ah, timeout=30)
    j = r.json()
    print(json.dumps({k: j.get(k) for k in ("id", "title", "status", "assigned_driver_id", "accepted_by", "offered_at", "cancelled_at")}))
elif cmd == "delete":
    for jid in sys.argv[2:]:
        r = requests.delete(f"{API}/jobs/{jid}", headers=ah, timeout=30)
        print(jid, r.status_code)
elif cmd == "list":
    r = requests.get(f"{API}/dispatch/board", headers=dh, timeout=60)
    for j in r.json()["jobs"]:
        print(j["id"], "|", j.get("title"), "|", j["status"], "|", j.get("facility_name"), "|", j.get("driver_name"))
