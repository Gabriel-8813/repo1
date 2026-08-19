import os, requests
from dotenv import dotenv_values
API = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}, timeout=30).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
jobs = requests.get(f"{API}/jobs", headers=h, timeout=30).json()
jobs = jobs["jobs"] if isinstance(jobs, dict) else jobs
mine = [j for j in jobs if (j.get("title") or "").startswith("TEST_QA drivermgmt") or "TEST_QA drivermgmt" in (j.get("description") or "")]
print("leftover mine:", [(j["id"], j.get("title"), j.get("status")) for j in mine])
for j in mine:
    print(requests.delete(f"{API}/jobs/{j['id']}", headers=h, timeout=30).status_code)
print("all TEST_ titles remaining:", sorted({(j.get('title'), j.get('status')) for j in jobs if (j.get('title') or '').startswith('TEST')}))
