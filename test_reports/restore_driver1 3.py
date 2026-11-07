import os, requests
from dotenv import dotenv_values
API = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}, timeout=30).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
d = requests.post(f"{API}/auth/login", json={"email": "driver1@test.com", "password": "Driver@123"}, timeout=30).json()
did = d["user"]["id"]
print(requests.put(f"{API}/drivers/{did}/record", json={"verification_status": "approved"}, headers=h, timeout=30).status_code)
recs = requests.get(f"{API}/admin/driver-verifications", headers=h, timeout=30).json()["drivers"]
print([r for r in recs if r["user_id"] == did][0])
