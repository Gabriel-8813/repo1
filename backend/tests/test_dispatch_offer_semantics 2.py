"""Iteration 15 — verification of FIX 1 (accepted_by only on real acceptance) and
FIX 2 (offered_at / cancelled_at drive dispatch board status_since)."""
import os
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{base_url.rstrip('/')}/api"

ACCOUNTS = {
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "driver": ("driver1@test.com", "Driver@123"),
}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    d = r.json()
    token = d.get("access_token") or d.get("token")
    assert token
    return token, d.get("user", {})


@pytest.fixture(scope="module")
def sess():
    return {k: login(*v) for k, v in ACCOUNTS.items()}


def hdr(sess, role):
    return {"Authorization": f"Bearer {sess[role][0]}"}


@pytest.fixture(scope="module")
def created_jobs():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(sess, created_jobs):
    yield
    h = hdr(sess, "admin")
    for jid in created_jobs:
        requests.delete(f"{API}/jobs/{jid}", headers=h, timeout=30)


def make_job(sess, created_jobs, title="TEST_IT15 offer semantics", **extra):
    payload = {
        "title": title,
        "description": "QA iteration15",
        "pickup_address": "455 Queen St W, Toronto, ON",
        "dropoff_address": "100 Queen St W, Toronto, ON",
        "item_category": "lab_sample",
        "recipient_name": "QA Lab",
        "recipient_phone": "416-555-0111",
        "payout_amount": 40.0,
        "distance_km": 4.0,
        "handling_flags": [],
    }
    payload.update(extra)
    r = requests.post(f"{API}/jobs", json=payload, headers=hdr(sess, "dispatcher"), timeout=60)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    job = r.json()
    created_jobs.append(job["id"])
    return job


def get_job_admin(sess, jid):
    r = requests.get(f"{API}/jobs/{jid}", headers=hdr(sess, "admin"), timeout=30)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def board_job(sess, jid):
    r = requests.get(f"{API}/dispatch/board", headers=hdr(sess, "dispatcher"), timeout=60)
    assert r.status_code == 200
    for j in r.json()["jobs"]:
        if j["id"] == jid:
            return j
    pytest.fail(f"job {jid} not on board")


# ---- FIX 1: accepted_by lifecycle ----
class TestAcceptedByLifecycle:
    def test_offer_does_not_set_accepted_by(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 offer no accepted_by")
        driver_id = sess["driver"][1]["id"]
        r = requests.put(f"{API}/jobs/{job['id']}",
                         json={"assigned_driver_id": driver_id, "status": "offered"},
                         headers=hdr(sess, "dispatcher"), timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["status"] == "offered"
        assert body.get("assigned_driver_id") == driver_id
        assert body.get("accepted_by") in (None, ""), f"accepted_by leaked at offer: {body.get('accepted_by')}"
        # persisted
        persisted = get_job_admin(sess, job["id"])
        assert persisted["status"] == "offered"
        assert persisted.get("assigned_driver_id") == driver_id
        assert persisted.get("accepted_by") in (None, "")

    def test_driver_sees_and_accepts_offered_job(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 driver accepts offer")
        driver_id = sess["driver"][1]["id"]
        requests.put(f"{API}/jobs/{job['id']}",
                     json={"assigned_driver_id": driver_id, "status": "offered"},
                     headers=hdr(sess, "dispatcher"), timeout=30).raise_for_status()
        dh = hdr(sess, "driver")
        # REGRESSION: visible in /jobs/my
        my = requests.get(f"{API}/jobs/my", headers=dh, timeout=30)
        assert my.status_code == 200
        assert job["id"] in [j["id"] for j in my.json()["jobs"]], "offered job missing from driver /jobs/my"
        # REGRESSION: visible in driver job list
        lst = requests.get(f"{API}/jobs", headers=dh, timeout=30)
        assert lst.status_code == 200
        payload = lst.json()
        arr = payload["jobs"] if isinstance(payload, dict) else payload
        assert job["id"] in [j["id"] for j in arr], "offered job missing from driver GET /api/jobs"
        # driver can read the job detail
        det = requests.get(f"{API}/jobs/{job['id']}", headers=dh, timeout=30)
        assert det.status_code == 200, f"driver cannot read offered job: {det.status_code}"
        # accept
        acc = requests.post(f"{API}/jobs/{job['id']}/accept", headers=dh, timeout=30)
        assert acc.status_code == 200, acc.text[:300]
        persisted = get_job_admin(sess, job["id"])
        assert persisted["status"] == "accepted"
        assert persisted.get("accepted_by") == driver_id, "accepted_by not set after driver accept"
        assert persisted.get("assigned_driver_id") == driver_id

    def test_reassign_accepted_job_clears_accepted_by(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 reassign clears accepted_by")
        driver_id = sess["driver"][1]["id"]
        requests.put(f"{API}/jobs/{job['id']}",
                     json={"assigned_driver_id": driver_id, "status": "offered"},
                     headers=hdr(sess, "dispatcher"), timeout=30).raise_for_status()
        requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(sess, "driver"), timeout=30).raise_for_status()
        assert get_job_admin(sess, job["id"]).get("accepted_by") == driver_id
        # re-offer same (only approved) driver -> accepted_by must clear
        r = requests.put(f"{API}/jobs/{job['id']}",
                         json={"assigned_driver_id": driver_id, "status": "offered"},
                         headers=hdr(sess, "dispatcher"), timeout=30)
        assert r.status_code == 200, r.text[:300]
        persisted = get_job_admin(sess, job["id"])
        assert persisted["status"] == "offered"
        assert persisted.get("accepted_by") in (None, ""), "accepted_by not cleared on re-offer"

    def test_staff_set_status_accepted_sets_accepted_by(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 staff accept sets accepted_by")
        driver_id = sess["driver"][1]["id"]
        r = requests.put(f"{API}/jobs/{job['id']}",
                         json={"assigned_driver_id": driver_id, "status": "accepted"},
                         headers=hdr(sess, "dispatcher"), timeout=30)
        assert r.status_code == 200, r.text[:300]
        persisted = get_job_admin(sess, job["id"])
        assert persisted["status"] == "accepted"
        assert persisted.get("accepted_by") == driver_id
        assert persisted.get("accepted_at")


# ---- FIX 2: offered_at / cancelled_at drive status_since ----
class TestStatusSinceClock:
    def test_offer_sets_offered_at_and_board_status_since(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 offered_at clock")
        created_at = get_job_admin(sess, job["id"])["created_at"]
        driver_id = sess["driver"][1]["id"]
        requests.put(f"{API}/jobs/{job['id']}",
                     json={"assigned_driver_id": driver_id, "status": "offered"},
                     headers=hdr(sess, "dispatcher"), timeout=30).raise_for_status()
        persisted = get_job_admin(sess, job["id"])
        assert persisted.get("offered_at"), "offered_at not set on offer"
        bj = board_job(sess, job["id"])
        assert bj["status"] == "offered"
        assert bj["status_since"] == persisted["offered_at"], (
            f"status_since {bj['status_since']} != offered_at {persisted['offered_at']}")
        assert bj["status_since"] != created_at or persisted["offered_at"] == created_at
        # sane, parseable, not in future
        ts = datetime.fromisoformat(bj["status_since"].replace("Z", "+00:00"))
        assert ts <= datetime.now(timezone.utc)

    def test_cancel_sets_cancelled_at_and_board_status_since(self, sess, created_jobs):
        job = make_job(sess, created_jobs, title="TEST_IT15 cancelled_at clock")
        r = requests.put(f"{API}/jobs/{job['id']}", json={"status": "cancelled"},
                         headers=hdr(sess, "dispatcher"), timeout=30)
        assert r.status_code == 200, r.text[:300]
        persisted = get_job_admin(sess, job["id"])
        assert persisted["status"] == "cancelled"
        assert persisted.get("cancelled_at"), "cancelled_at not set on cancel"
        bj = board_job(sess, job["id"])
        assert bj["status_since"] == persisted["cancelled_at"]
