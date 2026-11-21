import os, requests
from dotenv import dotenv_values
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
facs = requests.get(f"{API}/admin/facilities", headers=H).json()["facilities"]
for f in facs:
    print(f["name"], f["status"], f.get("per_delivery_rate"), f.get("commission_rate_override"), (f.get("owner") or {}).get("email"), f["volume"])
jobs = requests.get(f"{API}/admin/jobs", headers=H).json()
jl = jobs.get("jobs", jobs)
test_jobs = [j for j in jl if str(j.get("recipient_name", "")).startswith("TEST")]
print("leftover TEST jobs:", len(test_jobs))
for j in test_jobs:
    r = requests.delete(f"{API}/jobs/{j['id']}", headers=H)
    print("del", j["id"], r.status_code)
