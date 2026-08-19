import json
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
tok = requests.post(f"{BASE}/api/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r = requests.get(f"{BASE}/api/admin/jobs", headers=H)
data = r.json()
jobs = data if isinstance(data, list) else data.get("jobs", data)
print("type:", type(data), "count:", len(jobs))
for j in jobs:
    if not isinstance(j, dict):
        print("non-dict entry:", j)
        continue
    if "TEST_" in str(j.get("recipient_name")):
        print("TEST job:", j["id"], j.get("status"), j.get("recipient_name"))
        d = requests.delete(f"{BASE}/api/jobs/{j['id']}", headers=H)
        print("  delete ->", d.status_code, d.text[:120])
