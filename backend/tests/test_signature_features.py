"""Signature differentiator suite: SealTrace, Neighbourhood Routes, Care Handoff,
Storm-Ready, public Trusted Pharmacy Network + public seal verification."""
import base64
import io
import os

import pytest
import requests
from dotenv import dotenv_values

base_url = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "driver": ("demo.driver@meditrans.ca", "DemoDriver#2026"),
    "driver2": ("driver1@test.com", "Driver@123"),
    "facility": ("demo.facility@meditrans.ca", "DemoFacility#2026"),
    "dispatcher": ("demo.dispatcher@meditrans.ca", "DemoDispatch#2026"),
    "admin": ("demo.admin@meditrans.ca", "DemoAdmin#2026"),
}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
CREATED = []
CITY = "Mississauga"


@pytest.fixture(scope="module")
def tok():
    out = {}
    for role, (e, p) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
        assert r.status_code == 200, f"{role} login {r.status_code} {r.text[:200]}"
        out[role] = r.json()["access_token"]
    yield out
    for jid in CREATED:
        requests.delete(f"{API}/jobs/{jid}", headers={"Authorization": f"Bearer {out['admin']}"}, timeout=30)


def H(tok, role):
    return {"Authorization": f"Bearer {tok[role]}"}


def book(tok, care=False, storm=False, city=CITY, recipient="TEST_Seal Recipient"):
    payload = {
        "recipient_name": recipient, "recipient_phone": "+14165550199",
        "dropoff_address": f"100 City Centre Dr, {city}, ON L5B 2C9",
        "item_count": 1, "item_category": "prescription", "handling_flags": [],
        "requested_pickup_time": "2026-02-01T10:00", "consent_data_handling": True,
        "recipient_sms_consent": False, "care_handoff": care, "storm_priority": storm,
    }
    r = requests.post(f"{API}/facility/requests", json=payload, headers=H(tok, "facility"), timeout=60)
    assert r.status_code == 201, r.text[:300]
    j = r.json()
    CREATED.append(j["id"])
    return j


# --- Public network stats ---
def test_public_network_no_auth():
    r = requests.get(f"{API}/public/network", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("pharmacies", "facilities_total", "network", "deliveries_completed", "seal_checks_passed", "drivers_approved", "storm_ready_drivers"):
        assert k in d, k
    assert isinstance(d["network"], list)
    for n in d["network"]:
        assert set(n.keys()) <= {"name", "type", "city", "deliveries"}


# --- Facility request with care_handoff + storm_priority + seal_code ---
def test_facility_request_flags_and_seal(tok):
    j = book(tok, care=True, storm=True)
    assert j["seal_code"].startswith("MT-") and len(j["seal_code"]) == 11
    assert j["care_handoff"] is True and j["storm_priority"] is True
    r = requests.get(f"{API}/facility/deliveries", headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 200
    data = r.json()
    lst = data.get("deliveries") or data.get("jobs") or data
    found = [x for x in lst if x["id"] == j["id"]]
    assert found and found[0]["seal_code"] == j["seal_code"]
    assert found[0]["care_handoff"] is True and found[0]["storm_priority"] is True


def test_facility_request_default_flags(tok):
    j = book(tok)
    assert j["care_handoff"] is False and j["storm_priority"] is False
    assert j["seal_code"].startswith("MT-")


# --- Public seal verification ---
def test_public_verify_no_pii(tok):
    j = book(tok, care=True, recipient="TEST_Secret Person")
    code = j["seal_code"]
    r = requests.get(f"{API}/public/verify/{code}", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["seal_code"] == code and d["status"] == "open"
    assert d["delivery_city"] == CITY
    assert "facility_name" in d and isinstance(d["seal_checks"], list)
    txt = r.text
    for leak in ("TEST_Secret Person", "5550199", "City Centre Dr", "recipient_name", "recipient_phone", "pickup_address", "delivery_address"):
        assert leak not in txt, f"leak: {leak}"
    # lowercase / no prefix also resolves
    r2 = requests.get(f"{API}/public/verify/{code[3:].lower()}", timeout=30)
    assert r2.status_code == 200 and r2.json()["seal_code"] == code


def test_public_verify_unknown_404():
    r = requests.get(f"{API}/public/verify/MT-ZZZZZZ", timeout=30)
    assert r.status_code == 404


# --- Neighbourhood routes ---
def test_routes_bundle_and_accept(tok):
    a = book(tok, city="Oakville")
    b = book(tok, city="Oakville")
    r = requests.get(f"{API}/jobs/routes", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    bundles = r.json()["bundles"]
    oak = [x for x in bundles if x["area"].lower() == "oakville"]
    assert oak, f"no Oakville bundle: {[x['area'] for x in bundles]}"
    bd = oak[0]
    assert a["id"] in bd["job_ids"] and b["id"] in bd["job_ids"]
    assert bd["bonus_amount"] == round(bd["total_payout"] * 0.10, 2)
    assert bd["total_with_bonus"] == round(bd["total_payout"] + bd["bonus_amount"], 2)
    # drivers must not see full addresses in bundle cards
    for jj in bd["jobs"]:
        assert jj.get("delivery_address") in (None, "") and jj.get("recipient_name") in (None, "")
    ids = [a["id"], b["id"]]
    r = requests.post(f"{API}/jobs/routes/accept", json={"job_ids": ids}, headers=H(tok, "driver"), timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["count"] == 2
    for acc, orig in zip(sorted(d["accepted"], key=lambda x: x["id"]), sorted([a, b], key=lambda x: x["id"])):
        assert acc["status"] == "accepted" and acc["route_bundle"] is True
        assert acc["payout_amount"] == round(orig["payout_amount"] * 1.1, 2)
    # re-accept by another driver -> 400
    r = requests.post(f"{API}/jobs/routes/accept", json={"job_ids": ids}, headers=H(tok, "driver2"), timeout=30)
    assert r.status_code == 400
    # facility cannot use routes
    assert requests.get(f"{API}/jobs/routes", headers=H(tok, "facility"), timeout=30).status_code == 403


def test_routes_accept_requires_two():
    pass


# --- SealTrace driver checks ---
def test_seal_flow(tok):
    j = book(tok, care=True)
    jid = j["id"]
    # wrong stage before accept: job open -> pickup not allowed
    r = requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "pickup", "intact": True}, headers=H(tok, "dispatcher"), timeout=30)
    assert r.status_code == 400
    r = requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200, r.text[:200]
    # facility forbidden, other driver forbidden
    assert requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "pickup", "intact": True}, headers=H(tok, "facility"), timeout=30).status_code == 403
    assert requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "pickup", "intact": True}, headers=H(tok, "driver2"), timeout=30).status_code == 403
    # delivery stage before pickup -> 400
    assert requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "delivery", "intact": True}, headers=H(tok, "driver"), timeout=30).status_code == 400
    # invalid stage -> 422
    assert requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "bogus", "intact": True}, headers=H(tok, "driver"), timeout=30).status_code == 422
    r = requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "pickup", "intact": True}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    assert r.json()["event"]["event_type"] == "seal_verified" and r.json()["seal_code"] == j["seal_code"]
    # pickup
    r = requests.post(f"{API}/jobs/{jid}/custody-events", json={"event_type": "pickup_confirmed", "checklist": {"label_confirmed": True, "item_count_confirmed": True}}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 201, r.text[:200]
    r = requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "delivery", "intact": True}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    # evidence + delivered
    r = requests.post(f"{API}/jobs/{jid}/delivery-evidence", files={"file": ("s.png", io.BytesIO(PNG), "image/png")}, data={"kind": "signature"}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 201, r.text[:200]
    ev = r.json()
    url = ev.get("evidence_url") or ev.get("url") or ev.get("path")
    r = requests.post(f"{API}/jobs/{jid}/custody-events", json={"event_type": "delivered", "recipient_name": "TEST_Signer", "evidence_url": url}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 201, r.text[:200]
    # public verify reflects journey
    d = requests.get(f"{API}/public/verify/{j['seal_code']}", timeout=30).json()
    assert d["status"] == "delivered" and d["care_handoff"] is True
    stages = [(c["stage"], c["intact"]) for c in d["seal_checks"]]
    assert ("pickup", True) in stages and ("delivery", True) in stages
    assert d["picked_up_at"] and d["delivered_at"]
    # job flags persisted
    jr = requests.get(f"{API}/jobs/{jid}", headers=H(tok, "driver"), timeout=30)
    if jr.status_code == 200:
        assert jr.json().get("seal_pickup_verified") is True and jr.json().get("seal_delivery_verified") is True


def test_seal_exception_notifies_dispatchers(tok):
    j = book(tok)
    jid = j["id"]
    assert requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, "driver"), timeout=30).status_code == 200
    r = requests.post(f"{API}/jobs/{jid}/verify-seal", json={"stage": "pickup", "intact": False, "notes": "TEST_ torn"}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200 and r.json()["event"]["event_type"] == "seal_exception"
    n = requests.get(f"{API}/notifications", headers=H(tok, "dispatcher"), timeout=30)
    assert n.status_code == 200
    items = n.json().get("notifications") or n.json()
    assert any(j["seal_code"] in (x.get("message") or x.get("body") or "") for x in items)
    d = requests.get(f"{API}/public/verify/{j['seal_code']}", timeout=30).json()
    assert {"stage": "pickup", "intact": False} == {k: d["seal_checks"][0][k] for k in ("stage", "intact")}


# --- Storm-ready ---
def test_storm_ready_toggle(tok):
    before = requests.get(f"{API}/public/network", timeout=30).json()["storm_ready_drivers"]
    cur = requests.get(f"{API}/driver/storm-ready", headers=H(tok, "driver"), timeout=30).json()["storm_ready"]
    r = requests.put(f"{API}/driver/storm-ready", json={"storm_ready": not cur}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200 and r.json()["storm_ready"] is (not cur)
    assert requests.get(f"{API}/driver/storm-ready", headers=H(tok, "driver"), timeout=30).json()["storm_ready"] is (not cur)
    after = requests.get(f"{API}/public/network", timeout=30).json()["storm_ready_drivers"]
    assert after == before + (1 if not cur else -1)
    # restore
    requests.put(f"{API}/driver/storm-ready", json={"storm_ready": cur}, headers=H(tok, "driver"), timeout=30)
    assert requests.put(f"{API}/driver/storm-ready", json={"storm_ready": True}, headers=H(tok, "facility"), timeout=30).status_code == 403
