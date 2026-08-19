"""Cleanup TEST_ users/jobs created during iteration 10 UI testing."""
import os
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"

tok = requests.post(f"{API}/auth/login", json={"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}, timeout=30).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

users = requests.get(f"{API}/users", headers=H, timeout=30).json()
users = users.get("users", users if isinstance(users, list) else [])
for u in users:
    if str(u.get("email", "")).startswith("TEST_qa"):
        r = requests.delete(f"{API}/users/{u['id']}", headers=H, timeout=30)
        print("deleted user", u["email"], r.status_code)

jobs = requests.get(f"{API}/jobs", headers=H, timeout=30).json().get("jobs", [])
for j in jobs:
    if str(j.get("title", "")).startswith("TEST_QA"):
        r = requests.delete(f"{API}/jobs/{j['id']}", headers=H, timeout=30)
        print("deleted job", j["id"], r.status_code)
