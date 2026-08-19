"""Auth hardening checks: bcrypt hash format, brute-force lockout, admin seed."""
import os
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
benv = dotenv_values("/app/backend/.env")


def test_bcrypt_hash_format():
    client = MongoClient(benv["MONGO_URL"])
    db = client[benv["DB_NAME"]]
    u = db.users.find_one({"email": "facility1@test.com"})
    assert u, "facility1 user missing"
    pw = u.get("password") or u.get("password_hash") or u.get("hashed_password")
    assert pw and pw.startswith("$2b$"), f"hash prefix: {str(pw)[:6]}"


def test_login_rejects_wrong_password_401():
    r = requests.post(f"{API}/auth/login", json={"email": "facility1@test.com", "password": "wrong"}, timeout=30)
    assert r.status_code == 401, r.status_code


def test_brute_force_lockout_after_5_failures():
    codes = []
    for _ in range(6):
        r = requests.post(f"{API}/auth/login", json={"email": "facility1@test.com", "password": "wrongpass"}, timeout=30)
        codes.append(r.status_code)
    # valid password must still work if no lockout implemented
    ok = requests.post(f"{API}/auth/login", json={"email": "facility1@test.com", "password": "Facility@123"}, timeout=30)
    assert 423 in codes or 429 in codes, f"no lockout implemented; codes={codes}, valid-login-after={ok.status_code}"
