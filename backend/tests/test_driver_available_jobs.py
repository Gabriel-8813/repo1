"""Driver 'Available Jobs' hybrid pool feature tests.

Covers: GET /api/jobs/available masking + eligibility, POST /jobs/{id}/accept (status='accepted'),
POST /jobs/{id}/decline, offered-to-me flow, cancel/complete from 'accepted'.
"""
import os
import re
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "driver1": ("driver1@test.com", "Driver@123"),
    "facility1": ("facility1@test.com", "Facility@123"),
    "dispatcher1": ("dispatcher1@test.com", "Dispatch@123"),
}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"] if "access_token" in r.json() else r.json()["token"]


def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tokens():
    return {k: login(*v) for k, v in CREDS.items()}


@pytest.fixture(scope="module")
def driver1_id(tokens):
    r = requests.get(f"{API}/auth/me", headers=hdr(tokens["driver1"]), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def facility_id(tokens):
    r = requests.get(f"{API}/facilities", headers=hdr(tokens["facility1"]), timeout=30)
    assert r.status_code == 200, r.text
    facs = r.json().get("facilities", r.json() if isinstance(r.json(), list) else [])
    assert facs, "no facilities visible to facility1"
    return facs[0]["id"]


@pytest.fixture(scope="module")
def driver2(tokens):
    """Register a fresh second driver + approved driver record; cleaned up at teardown."""
    email = f"TEST_driver2_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{API}/auth/register", json={ "privacy_policy_accepted": True,
        "email": email, "password": "Driver@123", "full_name": "TEST Driver Two",
        "role": "driver", "phone": "6470000000"
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    token = body.get("access_token") or body.get("token")
    uid = body["user"]["id"] if "user" in body else requests.get(f"{API}/auth/me", headers=hdr(token), timeout=30).json()["id"]
    cr = requests.post(f"{API}/drivers", headers=hdr(tokens["admin"]), json={
        "user_id": uid, "verification_status": "approved", "cold_chain_certified": True
    }, timeout=30)
    assert cr.status_code == 201, cr.text
    yield {"id": uid, "token": token, "email": email}
    requests.delete(f"{API}/drivers/{uid}/record", headers=hdr(tokens["admin"]), timeout=30)
    requests.delete(f"{API}/admin/users/{uid}", headers=hdr(tokens["admin"]), timeout=30)


created_jobs = []


@pytest.fixture(scope="module", autouse=True)
def cleanup_jobs(tokens):
    yield
    for jid in created_jobs:
        requests.delete(f"{API}/admin/jobs/{jid}", headers=hdr(tokens["admin"]), timeout=30)
    # restore driver1 cold chain
    pass


def make_job(tokens, facility_id, **over):
    payload = {
        "title": "TEST_job " + uuid.uuid4().hex[:6],
        "pickup_address": "123 Queen St W, Toronto",
        "pickup_city": "Toronto",
        "delivery_address": "456 King St E, Toronto",
        "delivery_city": "Toronto",
        "facility_id": facility_id,
        "item_category": "lab_sample",
        "handling_flags": [],
        "distance_km": 7.5,
        "payout_amount": 42.5,
        "goods_type": "lab_sample",
        "urgency": "standard",
    }
    payload.update(over)
    r = requests.post(f"{API}/jobs", headers=hdr(tokens["facility1"]), json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    jid = r.json()["id"]
    created_jobs.append(jid)
    return jid


# ---- GET /jobs/available masking & shape ----
class TestAvailableMasking:
    def test_available_shape_and_masking(self, tokens, facility_id):
        jid = make_job(tokens, facility_id, handling_flags=["urgent", "signature_required"])
        r = requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        jobs = r.json()["jobs"]
        job = next((j for j in jobs if j["id"] == jid), None)
        assert job, f"created job {jid} not in available list"
        assert job["facility_name"], "facility_name missing"
        assert job["pickup_area"] == "Queen St W, Toronto", job["pickup_area"]
        assert job["dropoff_area"] == "King St E, Toronto", job["dropoff_area"]
        assert job["pickup_address"] is None
        assert job["delivery_address"] is None
        assert job["dropoff_address"] is None
        assert job["item_category"] == "lab_sample"
        assert job["handling_flags"] == ["urgent", "signature_required"]
        assert job["distance_km"] == 7.5
        assert job["payout_amount"] == 42.5
        assert "posted_by" not in job
        assert "declined_by" not in job
        assert all(s == "open" or (s == "offered") for s in [j["status"] for j in jobs])

    def test_only_open_or_offered_to_me(self, tokens, driver1_id):
        r = requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30)
        for j in r.json()["jobs"]:
            if j["status"] == "offered":
                assert j.get("assigned_driver_id") == driver1_id


# ---- Cold-chain eligibility ----
class TestColdChainEligibility:
    def test_cold_chain_hidden_when_not_certified(self, tokens, driver1_id, facility_id):
        cold_flag_job = make_job(tokens, facility_id, handling_flags=["cold_chain"], title="TEST_cold_flag")
        temp_job = make_job(tokens, facility_id, temperature_controlled=True, title="TEST_temp_ctrl")
        try:
            up = requests.put(f"{API}/drivers/{driver1_id}/record", headers=hdr(tokens["admin"]),
                              json={"cold_chain_certified": False}, timeout=30)
            assert up.status_code == 200, up.text
            assert up.json()["cold_chain_certified"] is False
            ids = [j["id"] for j in requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30).json()["jobs"]]
            assert cold_flag_job not in ids, "cold_chain job visible to non-certified driver"
            assert temp_job not in ids, "temperature_controlled job visible to non-certified driver"
        finally:
            r = requests.put(f"{API}/drivers/{driver1_id}/record", headers=hdr(tokens["admin"]),
                             json={"cold_chain_certified": True}, timeout=30)
            assert r.status_code == 200 and r.json()["cold_chain_certified"] is True
        ids = [j["id"] for j in requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30).json()["jobs"]]
        assert cold_flag_job in ids and temp_job in ids, "cold-chain jobs did not reappear after re-certification"


# ---- Accept ----
class TestAccept:
    def test_accept_sets_accepted_and_reveals_addresses(self, tokens, driver1_id, facility_id):
        jid = make_job(tokens, facility_id)
        r = requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        job = r.json()["job"]
        assert job["status"] == "accepted"
        assert job["accepted_at"]
        assert job["accepted_by"] == driver1_id
        assert job["assigned_driver_id"] == driver1_id
        assert job["pickup_address"] == "123 Queen St W, Toronto"
        assert job["delivery_address"] == "456 King St E, Toronto"

        my = requests.get(f"{API}/jobs/my", headers=hdr(tokens["driver1"]), timeout=30)
        assert my.status_code == 200
        mine = next(j for j in my.json()["jobs"] if j["id"] == jid)
        assert mine["status"] == "accepted"
        assert mine["pickup_address"] == "123 Queen St W, Toronto"
        assert mine["delivery_address"] == "456 King St E, Toronto"

        # not in available anymore
        ids = [j["id"] for j in requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30).json()["jobs"]]
        assert jid not in ids

        # cancel within grace -> free + reopened
        c = requests.post(f"{API}/jobs/{jid}/cancel", headers=hdr(tokens["driver1"]), timeout=30)
        assert c.status_code == 200, c.text
        assert c.json().get("charged") is False, c.json()
        adm = requests.get(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]), timeout=30).json()
        adm = adm.get("job", adm)
        assert adm["status"] == "open"
        assert adm["accepted_by"] is None and adm["assigned_driver_id"] is None

    def test_complete_from_accepted(self, tokens, facility_id):
        jid = make_job(tokens, facility_id, payout_amount=58.0)
        assert requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver1"]), timeout=30).status_code == 200
        r = requests.post(f"{API}/jobs/{jid}/complete", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "commission" in str(body).lower() or "driver_earnings" in body or "platform_fee" in body, body
        adm = requests.get(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]), timeout=30).json()
        adm = adm.get("job", adm)
        assert adm["status"] == "completed"
        assert adm["completed_at"] and adm["delivered_at"]


# ---- Decline ----
class TestDecline:
    def test_decline_open_job_hides_only_for_that_driver(self, tokens, facility_id, driver2):
        jid = make_job(tokens, facility_id)
        r = requests.post(f"{API}/jobs/{jid}/decline", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "declined"
        d1_ids = [j["id"] for j in requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30).json()["jobs"]]
        assert jid not in d1_ids
        d2 = requests.get(f"{API}/jobs/available", headers=hdr(driver2["token"]), timeout=30)
        assert d2.status_code == 200, d2.text
        assert jid in [j["id"] for j in d2.json()["jobs"]], "declined job hidden from other driver too"

    def test_decline_offered_reverts_to_open(self, tokens, driver1_id, facility_id):
        jid = make_job(tokens, facility_id)
        up = requests.put(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]),
                          json={"status": "offered", "assigned_driver_id": driver1_id}, timeout=30)
        assert up.status_code == 200, up.text
        avail = requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver1"]), timeout=30).json()["jobs"]
        offered = next((j for j in avail if j["id"] == jid), None)
        assert offered and offered["status"] == "offered", "offered-to-me job not in available pool"
        r = requests.post(f"{API}/jobs/{jid}/decline", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        adm = requests.get(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]), timeout=30).json()
        adm = adm.get("job", adm)
        assert adm["status"] == "open"
        assert adm["assigned_driver_id"] is None and adm["accepted_by"] is None
        assert driver1_id in (adm.get("declined_by") or [])

    def test_accept_offered_to_me(self, tokens, driver1_id, facility_id):
        jid = make_job(tokens, facility_id)
        up = requests.put(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]),
                          json={"status": "offered", "assigned_driver_id": driver1_id}, timeout=30)
        assert up.status_code == 200, up.text
        r = requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["job"]["status"] == "accepted"
        requests.post(f"{API}/jobs/{jid}/cancel", headers=hdr(tokens["driver1"]), timeout=30)

    def test_decline_accepted_job_400(self, tokens, facility_id):
        jid = make_job(tokens, facility_id)
        assert requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver1"]), timeout=30).status_code == 200
        r = requests.post(f"{API}/jobs/{jid}/decline", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"
        requests.post(f"{API}/jobs/{jid}/cancel", headers=hdr(tokens["driver1"]), timeout=30)

    def test_decline_rbac(self, tokens, facility_id):
        jid = make_job(tokens, facility_id)
        for role in ("facility1", "admin", "dispatcher1"):
            r = requests.post(f"{API}/jobs/{jid}/decline", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403, f"{role} got {r.status_code}"

    def test_decline_unknown_job_404(self, tokens):
        r = requests.post(f"{API}/jobs/{uuid.uuid4()}/decline", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 404, r.status_code


# ---- legacy in_progress compat ----
class TestLegacyStatus:
    def test_legacy_in_progress_can_complete(self, tokens, driver1_id, facility_id):
        jid = make_job(tokens, facility_id)
        assert requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver1"]), timeout=30).status_code == 200
        up = requests.put(f"{API}/jobs/{jid}", headers=hdr(tokens["admin"]), json={"status": "in_progress"}, timeout=30)
        assert up.status_code == 200, up.text
        r = requests.post(f"{API}/jobs/{jid}/complete", headers=hdr(tokens["driver1"]), timeout=30)
        assert r.status_code == 200, r.text
