import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
tok = requests.post(f"{API}/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
jobs = requests.get(f"{API}/jobs", headers=h).json()
jobs = jobs.get("jobs", jobs)
for j in jobs:
    rn = (j.get("recipient_name") or "")
    if rn.startswith("QA ") or rn.startswith("TEST_"):
        r = requests.delete(f"{API}/jobs/{j['id']}", headers=h)
        print("deleted", j["id"], rn, r.status_code)
users = requests.get(f"{API}/users", headers=h).json()
users = users.get("users", users)
for u in users:
    if (u.get("email") or "").startswith("TEST_"):
        print("stale test user", u["email"], requests.delete(f"{API}/users/{u['id']}", headers=h).status_code)
print("done")
