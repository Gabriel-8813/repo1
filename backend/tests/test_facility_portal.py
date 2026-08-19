"""Facility Portal — POST /api/facility/requests, masking, accept reveal, decline."""
import os
import time
import pytest
import requests
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

FACILITY = {"email": "facility1@test.com", "password": "Facility@123"}
DRIVER = {"email": "driver1@test.com", "password": "Driver@123"}
ADMIN = {"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}
FACILITY_ADDRESS_HINT = "455 Queen St W"


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token in login response: {r.json().keys()}"
    return tok


def hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def facility_token():
    return login(FACILITY)


@pytest.fixture(scope="module")
def driver_token():
    return login(DRIVER)


@pytest.fixture(scope="module")
def admin_token():
    return login(ADMIN)


@pytest.fixture(scope="module")
def created_jobs(admin_token):
    ids = []
    yield ids
    for jid in ids:
        requests.delete(f"{API}/jobs/{jid}", headers=hdr(admin_token), timeout=60)


def make_payload(**over):
    p = {
        "recipient_name": "TEST_Recipient Jane",
        "recipient_phone": "416-555-0199",
        "dropoff_address": "200 Elizabeth St, Toronto, ON",
        "item_count": 3,
        "item_category": "lab_sample",
        "handling_flags": ["cold_chain", "urgent"],
        "special_instructions": "TEST_ leave cooler at front desk",
        "requested_pickup_time": "2026-07-20T14:30",
    }
    p.update(over)
    return p


class TestFacilityRequestCreate:
    def test_create_defaults_and_payout(self, facility_token, created_jobs):
        r = requests.post(f"{API}/facility/requests", json=make_payload(), headers=hdr(facility_token), timeout=90)
        assert r.status_code == 201, r.text[:400]
        j = r.json()
        created_jobs.append(j["id"])
        assert "_id" not in j
        assert j["status"] == "open"
        assert j["assigned_driver_id"] is None
        assert FACILITY_ADDRESS_HINT.lower() in (j["pickup_address"] or "").lower(), j["pickup_address"]
        assert j["delivery_address"] == "200 Elizabeth St, Toronto, ON"
        assert isinstance(j["distance_km"], (int, float)) and j["distance_km"] > 0
        assert j["item_count"] == 3
        assert j["item_category"] == "lab_sample"
        assert set(j["handling_flags"]) == {"cold_chain", "urgent"}
        assert j["temperature_controlled"] is True
        assert j["urgency"] == "urgent"
        assert j["requested_pickup_time"] == "2026-07-20T14:30"
        # payout math: max(25, 1.5*km) * 1.5 + 15
        km = j["distance_km"]
        expected = round(max(25.0, 1.5 * km) * 1.5 + 15.0, 2)
        assert j["payout_amount"] == expected, f"km={km} payout={j['payout_amount']} expected={expected}"
        assert j["offered_price"] == j["payout_amount"]
        assert isinstance(j["distance_estimated"], bool)

    def test_create_no_flags_min_fee(self, facility_token, created_jobs):
        time.sleep(1.2)  # Nominatim rate limit
        r = requests.post(f"{API}/facility/requests",
                          json=make_payload(handling_flags=[], item_category="prescription",
                                            dropoff_address="100 Queen St W, Toronto, ON"),
                          headers=hdr(facility_token), timeout=90)
        assert r.status_code == 201, r.text[:400]
        j = r.json()
        created_jobs.append(j["id"])
        assert j["temperature_controlled"] is False
        assert j["urgency"] == "standard"
        assert j["payout_amount"] == round(max(25.0, 1.5 * j["distance_km"]), 2)

    def test_explicit_pickup_address_used(self, facility_token, created_jobs):
        time.sleep(1.2)
        r = requests.post(f"{API}/facility/requests",
                          json=make_payload(pickup_address="1 Dundas St E, Toronto, ON"),
                          headers=hdr(facility_token), timeout=90)
        assert r.status_code == 201, r.text[:400]
        j = r.json()
        created_jobs.append(j["id"])
        assert j["pickup_address"] == "1 Dundas St E, Toronto, ON"

    def test_invalid_category_422(self, facility_token):
        r = requests.post(f"{API}/facility/requests", json=make_payload(item_category="drugs"),
                          headers=hdr(facility_token), timeout=60)
        assert r.status_code == 422, r.text[:300]

    def test_invalid_flag_422(self, facility_token):
        r = requests.post(f"{API}/facility/requests", json=make_payload(handling_flags=["hazmat"]),
                          headers=hdr(facility_token), timeout=60)
        assert r.status_code == 422, r.text[:300]

    def test_driver_forbidden_403(self, driver_token):
        r = requests.post(f"{API}/facility/requests", json=make_payload(), headers=hdr(driver_token), timeout=60)
        assert r.status_code == 403, r.text[:300]

    def test_unauthenticated_401(self):
        r = requests.post(f"{API}/facility/requests", json=make_payload(), timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_facility_without_profile_400(self, admin_token):
        email = "TEST_nofac@test.com"
        cr = requests.post(f"{API}/users", json={
            "name": "TEST_No Facility", "email": email, "phone": "416-555-0000",
            "password": "NoFac@1234", "role": "facility"
        }, headers=hdr(admin_token), timeout=60)
        assert cr.status_code in (200, 201), cr.text[:300]
        uid = cr.json().get("id") or cr.json().get("user", {}).get("id")
        try:
            tok = login({"email": email, "password": "NoFac@1234"})
            r = requests.post(f"{API}/facility/requests", json=make_payload(), headers=hdr(tok), timeout=60)
            assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
            assert "facility" in r.json().get("detail", "").lower()
        finally:
            if uid:
                requests.delete(f"{API}/users/{uid}", headers=hdr(admin_token), timeout=60)


class TestDriverMaskingAndAccept:
    def test_masking_then_accept_reveals(self, facility_token, driver_token, created_jobs, admin_token):
        time.sleep(1.2)
        r = requests.post(f"{API}/facility/requests", json=make_payload(), headers=hdr(facility_token), timeout=90)
        assert r.status_code == 201, r.text[:400]
        job = r.json()
        jid = job["id"]
        created_jobs.append(jid)

        av = requests.get(f"{API}/jobs/available", headers=hdr(driver_token), timeout=60)
        assert av.status_code == 200, av.text[:300]
        found = [j for j in av.json()["jobs"] if j["id"] == jid]
        assert found, "new offered job not visible to driver1 in /jobs/available"
        d = found[0]
        assert d["pickup_address"] is None
        assert d["delivery_address"] is None
        assert d.get("dropoff_address") is None
        assert d["recipient_name"] is None
        assert d["recipient_phone"] is None
        assert d["pickup_area"] and d["dropoff_area"]
        assert FACILITY_ADDRESS_HINT not in d["pickup_area"]
        assert d["item_count"] == 3
        assert d["requested_pickup_time"] == "2026-07-20T14:30"
        assert d["payout_amount"] == job["payout_amount"]

        acc = requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(driver_token), timeout=60)
        assert acc.status_code == 200, acc.text[:400]
        a = acc.json().get("job", acc.json())
        assert a["status"] in ("accepted", "in_progress")
        assert FACILITY_ADDRESS_HINT.lower() in (a["pickup_address"] or "").lower()
        assert a["delivery_address"] == "200 Elizabeth St, Toronto, ON"
        assert a["recipient_name"] == "TEST_Recipient Jane"
        assert a["recipient_phone"] == "416-555-0199"

        # persisted reveal via GET
        g = requests.get(f"{API}/jobs/{jid}", headers=hdr(driver_token), timeout=60)
        assert g.status_code == 200
        gj = g.json().get("job", g.json())
        assert gj["recipient_name"] == "TEST_Recipient Jane"

    def test_decline_removes_from_queue(self, facility_token, driver_token, created_jobs):
        time.sleep(1.2)
        r = requests.post(f"{API}/facility/requests", json=make_payload(handling_flags=["fragile"]),
                          headers=hdr(facility_token), timeout=90)
        assert r.status_code == 201, r.text[:400]
        jid = r.json()["id"]
        created_jobs.append(jid)

        av = requests.get(f"{API}/jobs/available", headers=hdr(driver_token), timeout=60)
        assert any(j["id"] == jid for j in av.json()["jobs"])

        dec = requests.post(f"{API}/jobs/{jid}/decline", headers=hdr(driver_token), timeout=60)
        assert dec.status_code == 200, dec.text[:300]

        av2 = requests.get(f"{API}/jobs/available", headers=hdr(driver_token), timeout=60)
        assert not any(j["id"] == jid for j in av2.json()["jobs"]), "declined job still in driver queue"

        # status unchanged (still in the open pool) — verify as facility owner
        fac = requests.get(f"{API}/jobs/{jid}", headers=hdr(login(FACILITY)), timeout=60)
        assert fac.status_code == 200
        fj = fac.json().get("job", fac.json())
        assert fj["status"] == "open", fj["status"]
        assert fj["assigned_driver_id"] is None
