"""Dispatcher Console backend tests — GET /api/dispatch/board, PUT /api/jobs/{id} (assign/reassign/cancel),
GET /api/jobs/{id}/custody-events staff access, RBAC."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

CREDS_FILE = Path("/app/memory/test_credentials.md")

ACCOUNTS = {
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "driver": ("driver1@test.com", "Driver@123"),
    "newdriver": ("newdriver@test.com", "NewDriver@123"),
    "facility": ("facility1@test.com", "Facility@123"),
}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"no token in login response: {list(data.keys())}"
    return token, data.get("user", {})


@pytest.fixture(scope="session")
def creds_present():
    assert CREDS_FILE.exists(), "missing /app/memory/test_credentials.md"
    return CREDS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def tokens(creds_present):
    out = {}
    for k, (e, p) in ACCOUNTS.items():
        out[k] = login(e, p)
    return out


def hdr(tokens, role):
    return {"Authorization": f"Bearer {tokens[role][0]}"}


@pytest.fixture(scope="module")
def created_jobs():
    ids = []
    yield ids


@pytest.fixture(scope="module", autouse=True)
def cleanup(tokens, created_jobs):
    yield
    h = hdr(tokens, "admin")
    for jid in created_jobs:
        requests.delete(f"{API}/jobs/{jid}", headers=h, timeout=30)


def make_job(tokens, created_jobs, title="TEST_QA dispatch job", **extra):
    payload = {
        "title": title,
        "description": "QA dispatch console test job",
        "pickup_address": "455 Queen St W, Toronto, ON",
        "dropoff_address": "100 Queen St W, Toronto, ON",
        "item_category": "lab_sample",
        "recipient_name": "QA Lab",
        "recipient_phone": "416-555-0111",
        "payout_amount": 42.5,
        "distance_km": 5.0,
        "handling_flags": [],
    }
    payload.update(extra)
    r = requests.post(f"{API}/jobs", json=payload, headers=hdr(tokens, "dispatcher"), timeout=60)
    assert r.status_code in (200, 201), f"job create failed: {r.status_code} {r.text[:400]}"
    job = r.json()
    assert "_id" not in job
    created_jobs.append(job["id"])
    return job


# ---------------- GET /api/dispatch/board ----------------
class TestDispatchBoard:
    def test_board_rbac(self, tokens):
        for role in ("dispatcher", "admin"):
            r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, role), timeout=60)
            assert r.status_code == 200, f"{role}: {r.status_code} {r.text[:300]}"
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, role), timeout=60)
            assert r.status_code == 403, f"{role} should be forbidden, got {r.status_code}"
        r = requests.get(f"{API}/dispatch/board", timeout=60)
        assert r.status_code in (401, 403)

    def test_board_shape(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA board shape")
        r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("jobs"), list)
        assert isinstance(data.get("approved_drivers"), list)
        # approved drivers include driver1
        names = {d["user_id"]: d["name"] for d in data["approved_drivers"]}
        assert tokens["driver"][1]["id"] in names, "approved driver1 missing from approved_drivers"
        assert tokens["newdriver"][1]["id"] not in names, "unverified driver leaked into approved_drivers"
        mine = [j for j in data["jobs"] if j["id"] == job["id"]]
        assert len(mine) == 1
        j = mine[0]
        assert "_id" not in j
        for key in ("facility_name", "driver_name", "status_since", "status"):
            assert key in j, f"missing {key}"
        assert j["driver_name"] is None
        assert re.match(r"^\d{4}-\d{2}-\d{2}T", j["status_since"]), j["status_since"]

    def test_board_facility_name_populated(self, tokens):
        r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, "dispatcher"), timeout=60)
        jobs = r.json()["jobs"]
        with_fac = [j for j in jobs if j.get("facility_id")]
        if with_fac:
            assert any(j.get("facility_name") for j in with_fac), "facility_name never resolved"


# ---------------- assign / reassign / cancel ----------------
class TestAssignCancel:
    def test_assign_approved_driver(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA assign")
        did = tokens["driver"][1]["id"]
        r = requests.put(f"{API}/jobs/{job['id']}",
                         json={"assigned_driver_id": did, "status": "offered"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert body["status"] == "offered"
        assert body["assigned_driver_id"] == did
        # persistence + board reflects driver name
        g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens, "dispatcher"), timeout=60)
        assert g.status_code == 200
        assert g.json()["assigned_driver_id"] == did
        assert g.json()["status"] == "offered"
        board = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, "dispatcher"), timeout=60).json()
        bj = next(x for x in board["jobs"] if x["id"] == job["id"])
        assert bj["driver_name"], "driver_name not resolved on board after assign"

    def test_assign_unverified_driver_400(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA unverified")
        r = requests.put(f"{API}/jobs/{job['id']}",
                         json={"assigned_driver_id": tokens["newdriver"][1]["id"], "status": "offered"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:300]}"
        assert "approved" in r.json().get("detail", "").lower()
        g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens, "dispatcher"), timeout=60).json()
        assert g["status"] != "offered" or not g.get("assigned_driver_id")

    def test_offer_without_driver_400(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA nodriver")
        r = requests.put(f"{API}/jobs/{job['id']}", json={"status": "offered"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:300]}"
        assert "driver" in r.json().get("detail", "").lower()

    def test_reassign_to_second_driver(self, tokens, created_jobs):
        """Temporarily approve newdriver so we have 2 approved drivers, then revert."""
        admin_h = hdr(tokens, "admin")
        nd = tokens["newdriver"][1]["id"]
        orig = requests.get(f"{API}/drivers/{nd}/record", headers=admin_h, timeout=60)
        assert orig.status_code == 200, orig.text[:200]
        orig_status = orig.json().get("verification_status", "incomplete")
        up = requests.put(f"{API}/drivers/{nd}/record", json={"verification_status": "approved"},
                          headers=admin_h, timeout=60)
        assert up.status_code == 200, up.text[:300]
        try:
            board = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, "dispatcher"), timeout=60).json()
            approved = {d["user_id"] for d in board["approved_drivers"]}
            assert nd in approved, "newly approved driver not reflected in board approved_drivers"
            job = make_job(tokens, created_jobs, title="TEST_QA reassign")
            d1, d2 = tokens["driver"][1]["id"], nd
            self._reassign(tokens, job, d1, d2)
        finally:
            requests.put(f"{API}/drivers/{nd}/record", json={"verification_status": orig_status},
                         headers=admin_h, timeout=60)

    def _reassign(self, tokens, job, d1, d2):
        r1 = requests.put(f"{API}/jobs/{job['id']}", json={"assigned_driver_id": d1, "status": "offered"},
                          headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r1.status_code == 200
        r2 = requests.put(f"{API}/jobs/{job['id']}", json={"assigned_driver_id": d2, "status": "offered"},
                          headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:300]}"
        g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens, "dispatcher"), timeout=60).json()
        assert g["assigned_driver_id"] == d2
        assert not g.get("accepted_by"), "accepted_by must stay unset until the driver actually accepts"

    def test_cancel_job(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA cancel")
        r = requests.put(f"{API}/jobs/{job['id']}", json={"status": "cancelled"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["status"] == "cancelled"
        g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens, "dispatcher"), timeout=60).json()
        assert g["status"] == "cancelled"

    def test_cancel_assigned_job(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA cancel assigned")
        did = tokens["driver"][1]["id"]
        requests.put(f"{API}/jobs/{job['id']}", json={"assigned_driver_id": did, "status": "offered"},
                     headers=hdr(tokens, "dispatcher"), timeout=60)
        r = requests.put(f"{API}/jobs/{job['id']}", json={"status": "cancelled"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["status"] == "cancelled"

    def test_invalid_status_rejected(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA badstatus")
        r = requests.put(f"{API}/jobs/{job['id']}", json={"status": "teleported"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code in (400, 422), f"got {r.status_code}"

    def test_update_missing_job_404(self, tokens):
        r = requests.put(f"{API}/jobs/does-not-exist-qa", json={"status": "cancelled"},
                         headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 404


# ---------------- custody events staff access ----------------
class TestCustodyStaffAccess:
    def test_staff_can_read_custody_of_foreign_job(self, tokens, created_jobs):
        # job posted by facility user (not the dispatcher)
        payload = {
            "facility_type": "lab", "dropoff_address": "100 Queen St W, Toronto, ON",
            "item_category": "lab_sample", "item_count": 1,
            "recipient_name": "QA Lab", "recipient_phone": "416-555-0122",
            "handling_flags": [], "urgency": "standard",
            "requested_pickup_time": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        }
        r = requests.post(f"{API}/facility/requests", json=payload, headers=hdr(tokens, "facility"), timeout=90)
        if r.status_code not in (200, 201):
            pytest.skip(f"facility request create unavailable: {r.status_code} {r.text[:200]}")
        jid = r.json()["id"]
        created_jobs.append(jid)
        for role in ("dispatcher", "admin"):
            g = requests.get(f"{API}/jobs/{jid}/custody-events", headers=hdr(tokens, role), timeout=60)
            assert g.status_code == 200, f"{role}: {g.status_code} {g.text[:300]}"
            body = g.json()
            assert isinstance(body.get("custody_events"), list)
            assert all("_id" not in e for e in body["custody_events"])

    def test_custody_unrelated_driver_403(self, tokens, created_jobs):
        job = make_job(tokens, created_jobs, title="TEST_QA custody rbac")
        g = requests.get(f"{API}/jobs/{job['id']}/custody-events", headers=hdr(tokens, "newdriver"), timeout=60)
        assert g.status_code == 403, f"got {g.status_code}"

    def test_custody_missing_job_404(self, tokens):
        g = requests.get(f"{API}/jobs/nope-qa/custody-events", headers=hdr(tokens, "dispatcher"), timeout=60)
        assert g.status_code == 404
