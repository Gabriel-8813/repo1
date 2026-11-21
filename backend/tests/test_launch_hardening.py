"""Launch-readiness security hardening (Phase 1) regression suite:
E2E delivery flow, job state machine, admin-only complete, dispatcher transitions,
auth/suspension, download tokens, review confirm_token, facility gating, twilio webhook,
atomic accept, upload magic-byte checks. Self-cleaning (open jobs / TEST_ users / TEST_ facilities)."""
import base64
import concurrent.futures
import io
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

base_url = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
API = f"{base_url.rstrip('/')}/api"
benv = dotenv_values("/app/backend/.env")
DB = MongoClient(benv["MONGO_URL"])[benv["DB_NAME"]]

CREDS = {
    "driver": ("demo.driver@meditrans.ca", "DemoDriver#2026"),
    "driver2": ("driver1@test.com", "Driver@123"),
    "facility": ("demo.facility@meditrans.ca", "DemoFacility#2026"),
    "dispatcher": ("demo.dispatcher@meditrans.ca", "DemoDispatch#2026"),
    "admin": ("demo.admin@meditrans.ca", "DemoAdmin#2026"),
}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
CREATED_JOBS, CREATED_USERS, CREATED_FACS = [], [], []
STATE = {}


@pytest.fixture(scope="module")
def tok():
    out = {}
    for role, (e, p) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
        assert r.status_code == 200, f"{role} login {r.status_code} {r.text[:200]}"
        out[role] = r.json()["access_token"]
        out[role + "_id"] = r.json()["user"]["id"]
    yield out
    for jid in CREATED_JOBS:
        j = DB.jobs.find_one({"id": jid}, {"status": 1})
        if j and j.get("status") == "open":
            requests.delete(f"{API}/jobs/{jid}", headers={"Authorization": f"Bearer {out['admin']}"}, timeout=30)
    if STATE.get("review_id"):
        DB.reviews.delete_one({"id": STATE["review_id"]})
    for fid in CREATED_FACS:
        DB.facilities.delete_one({"id": fid, "name": {"$regex": "^TEST_"}})
    for uid in CREATED_USERS:
        DB.users.delete_one({"id": uid, "email": {"$regex": "^test_"}})
        DB.drivers.delete_one({"user_id": uid})


def H(tok, role):
    return {"Authorization": f"Bearer {tok[role]}"}


def book(tok, facility_id=None, role="facility", expect=201):
    payload = {
        "recipient_name": "TEST_Hardening Recipient", "recipient_phone": "+14165550199",
        "dropoff_address": "100 Queen St W, Toronto, ON M5H 2N2",
        "item_count": 1, "item_category": "prescription", "handling_flags": [],
        "requested_pickup_time": "2026-02-01T10:00", "consent_data_handling": True,
        "recipient_sms_consent": False,
    }
    if facility_id:
        payload["facility_id"] = facility_id
    r = requests.post(f"{API}/facility/requests", json=payload, headers=H(tok, role), timeout=60)
    assert r.status_code == expect, r.text[:300]
    if expect == 201:
        CREATED_JOBS.append(r.json()["id"])
        return r.json()
    return r


# --- E2E happy path: book -> jobs list -> accept -> pickup -> evidence -> delivered -> commission once ---
def test_e2e_delivery_flow(tok):
    job = book(tok)
    jid = job["id"]
    r = requests.get(f"{API}/jobs", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    data = r.json()
    jobs = data if isinstance(data, list) else (data.get("jobs") or data.get("items") or [])
    assert any(j["id"] == jid for j in jobs), "new job not visible in driver /jobs"
    r = requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["job"]["status"] == "accepted"
    r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tok, "driver"), timeout=30,
                      json={"event_type": "pickup_confirmed", "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
    assert r.status_code == 201, r.text
    assert r.json()["job_status"] == "picked_up"
    # spoofed upload: text claiming png -> 422
    r = requests.post(f"{API}/jobs/{jid}/delivery-evidence", headers=H(tok, "driver"), timeout=30,
                      files={"file": ("sig.png", io.BytesIO(b"hello not a png"), "image/png")}, data={"kind": "signature"})
    assert r.status_code == 422, r.text
    r = requests.post(f"{API}/jobs/{jid}/delivery-evidence", headers=H(tok, "driver"), timeout=60,
                      files={"file": ("sig.png", io.BytesIO(PNG), "image/png")}, data={"kind": "signature"})
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["evidence_url"].endswith("/file")
    STATE["evidence_url"], STATE["evidence_id"] = ev["evidence_url"], ev["evidence_id"]
    r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tok, "driver"), timeout=30,
                      json={"event_type": "delivered", "recipient_name": "TEST_Recv", "evidence_url": ev["evidence_url"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job_status"] == "delivered"
    assert body["settlement"]["commission_charged"] > 0
    # second delivered must be rejected
    r2 = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tok, "driver"), timeout=30,
                       json={"event_type": "delivered", "recipient_name": "TEST_Recv", "evidence_url": ev["evidence_url"]})
    assert r2.status_code == 400
    assert DB.ledger.count_documents({"job_id": jid, "type": "commission"}) == 1
    j = DB.jobs.find_one({"id": jid})
    assert j["status"] == "delivered" and j.get("confirm_token")
    STATE["delivered_job"], STATE["confirm_token"] = jid, j["confirm_token"]


def test_delivered_job_immutable_and_undeletable(tok):
    jid = STATE["delivered_job"]
    r = requests.put(f"{API}/jobs/{jid}", json={"payout_amount": 1}, headers=H(tok, "admin"), timeout=30)
    assert r.status_code == 403
    r = requests.delete(f"{API}/jobs/{jid}", headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 400


# --- Download tokens ---
def test_download_tokens(tok):
    ev_url = STATE["evidence_url"]
    base = API[:-4]
    r = requests.get(f"{API}/auth/download-token", headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 200 and r.json()["expires_in"] == 300
    dl = r.json()["token"]
    # download token usable as session? -> 401
    assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {dl}"}, timeout=30).status_code == 401
    r = requests.get(f"{base}{ev_url}?auth={dl}", timeout=30)
    assert r.status_code == 200 and r.content[:8] == PNG[:8]
    assert requests.get(f"{base}{ev_url}?auth={tok['facility']}", timeout=30).status_code == 401
    assert requests.get(f"{base}{ev_url}", headers=H(tok, "facility"), timeout=30).status_code == 200
    # billing export
    assert requests.get(f"{API}/facility/billing/export?format=csv&auth={dl}", timeout=30).status_code == 200
    assert requests.get(f"{API}/facility/billing/export?format=csv&auth={tok['facility']}", timeout=30).status_code == 401
    assert requests.get(f"{API}/facility/billing/export?format=csv", headers=H(tok, "facility"), timeout=30).status_code == 200
    # custody PDF (admin)
    jid = STATE["delivered_job"]
    adl = requests.get(f"{API}/auth/download-token", headers=H(tok, "admin"), timeout=30).json()["token"]
    r = requests.get(f"{API}/jobs/{jid}/custody-record/pdf?auth={adl}", timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert requests.get(f"{API}/jobs/{jid}/custody-record/pdf?auth={tok['admin']}", timeout=30).status_code == 401
    assert requests.get(f"{API}/jobs/{jid}/custody-record/pdf", headers=H(tok, "admin"), timeout=60).status_code == 200


# --- Reviews confirm_token ---
def test_review_confirm_token(tok):
    jid = STATE["delivered_job"]
    r = requests.post(f"{API}/reviews/{jid}", json={"rating": 5, "comment": "TEST_"}, timeout=30)
    assert r.status_code in (400, 403)
    r = requests.post(f"{API}/reviews/{jid}", json={"rating": 5, "comment": "TEST_", "confirm_token": "wrong"}, timeout=30)
    assert r.status_code == 403
    r = requests.post(f"{API}/reviews/{jid}", json={"rating": 5, "comment": "TEST_review", "confirm_token": STATE["confirm_token"]}, timeout=30)
    assert r.status_code == 200, r.text
    STATE["review_id"] = r.json()["review"]["id"]


def test_driver_sees_confirm_token(tok):
    """Informational: driver API response exposes confirm_token (tip link) -> driver can self-review."""
    jid = STATE["delivered_job"]
    r = requests.get(f"{API}/jobs/{jid}", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    STATE["driver_sees_token"] = r.json().get("confirm_token") == STATE["confirm_token"]
    print("DRIVER_SEES_CONFIRM_TOKEN", STATE["driver_sees_token"])


# --- Job state machine / RBAC ---
def test_job_update_rules(tok):
    job = book(tok)
    jid = job["id"]
    assert requests.put(f"{API}/jobs/{jid}", json={"notes": "x"}, headers=H(tok, "driver"), timeout=30).status_code == 403
    assert requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, "driver"), timeout=30).status_code == 200
    assert requests.put(f"{API}/jobs/{jid}", json={"status": "delivered"}, headers=H(tok, "driver"), timeout=30).status_code == 403
    assert requests.put(f"{API}/jobs/{jid}", json={"payout_amount": 999}, headers=H(tok, "facility"), timeout=30).status_code == 403
    assert requests.put(f"{API}/jobs/{jid}", json={"dropoff_address": "1 Evil St, Toronto"}, headers=H(tok, "facility"), timeout=30).status_code == 403
    assert requests.delete(f"{API}/jobs/{jid}", headers=H(tok, "facility"), timeout=30).status_code == 400
    # complete: driver 403, admin no reason 422, admin with reason 200
    assert requests.post(f"{API}/jobs/{jid}/complete", json={"reason": "manual test"}, headers=H(tok, "driver"), timeout=30).status_code == 403
    assert requests.post(f"{API}/jobs/{jid}/complete", json={}, headers=H(tok, "admin"), timeout=30).status_code == 422
    r = requests.post(f"{API}/jobs/{jid}/complete", json={"reason": "TEST_ manual settle"}, headers=H(tok, "admin"), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["job"]["status"] == "completed"
    assert DB.ledger.count_documents({"job_id": jid, "type": "commission"}) == 1
    assert requests.post(f"{API}/jobs/{jid}/complete", json={"reason": "TEST_ again"}, headers=H(tok, "admin"), timeout=30).status_code == 400


def test_delete_open_job_by_poster(tok):
    job = book(tok)
    r = requests.delete(f"{API}/jobs/{job['id']}", headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 200
    assert DB.jobs.find_one({"id": job["id"]}) is None


def test_dispatcher_transitions(tok):
    job = book(tok)
    jid = job["id"]
    d = H(tok, "dispatcher")
    r = requests.put(f"{API}/jobs/{jid}", json={"status": "offered", "assigned_driver_id": tok["driver_id"]}, headers=d, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "offered"
    for bad in ("picked_up", "delivered"):
        assert requests.put(f"{API}/jobs/{jid}", json={"status": bad}, headers=d, timeout=30).status_code == 400
    r = requests.put(f"{API}/jobs/{jid}", json={"status": "open"}, headers=d, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "open"
    r = requests.put(f"{API}/jobs/{jid}", json={"status": "cancelled"}, headers=d, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # accepted -> cancelled
    job2 = book(tok)
    assert requests.post(f"{API}/jobs/{job2['id']}/accept", headers=H(tok, "driver"), timeout=30).status_code == 200
    r = requests.put(f"{API}/jobs/{job2['id']}", json={"status": "cancelled"}, headers=d, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


# --- Atomic accept ---
def test_atomic_accept(tok):
    job = book(tok)
    jid = job["id"]

    def acc(role):
        return requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, role), timeout=30).status_code
    results = []
    for _ in range(1):
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            results = list(ex.map(acc, ["driver", "driver2"]))
    print("ATOMIC", results)
    assert sorted(results) in ([200, 400], [200, 409]), results
    assert results.count(200) == 1
    # cancel to keep the pool tidy
    requests.put(f"{API}/jobs/{jid}", json={"status": "cancelled"}, headers=H(tok, "dispatcher"), timeout=30)


# --- Auth ---
def test_auth_rules(tok):
    em = f"test_hard_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": em, "password": "short", "full_name": "TEST_ U", "phone": "+14165550100", "privacy_policy_accepted": True}, timeout=30)
    assert r.status_code == 422
    r = requests.post(f"{API}/auth/register", json={"email": em, "password": "LongPass#2026", "full_name": "TEST_ U", "phone": "+14165550100", "privacy_policy_accepted": True}, timeout=30)
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user"]["id"]
    CREATED_USERS.append(uid)
    r = requests.post(f"{API}/auth/register", json={"email": em.upper().replace("EXAMPLE.COM", "Example.com"), "password": "LongPass#2026", "full_name": "TEST_ U", "phone": "+14165550100", "privacy_policy_accepted": True}, timeout=30)
    assert r.status_code == 400
    r = requests.post(f"{API}/auth/login", json={"email": "Demo.Driver@meditrans.ca", "password": "DemoDriver#2026"}, timeout=30)
    assert r.status_code == 200
    r = requests.post(f"{API}/auth/login", json={"email": em, "password": "LongPass#2026"}, timeout=30)
    assert r.status_code == 200
    utok = r.json()["access_token"]
    DB.users.update_one({"id": uid}, {"$set": {"status": "suspended"}, "$inc": {"token_version": 1}})
    assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {utok}"}, timeout=30).status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": em, "password": "LongPass#2026"}, timeout=30).status_code == 403


# --- Facility gating ---
def test_facility_pending_gating(tok):
    r = requests.post(f"{API}/facilities", headers=H(tok, "facility"), timeout=30, json={
        "name": "TEST_Pending Clinic", "type": "pharmacy", "address": "1 Test St, Toronto, ON",
        "contact_name": "TEST_ C", "contact_email": "test_c@example.com", "contact_phone": "+14165550111",
        "billing_email": "test_b@example.com", "status": "approved"})
    assert r.status_code == 201, r.text
    fac = r.json()
    CREATED_FACS.append(fac["id"])
    assert fac["status"] == "pending"
    r = book(tok, facility_id=fac["id"], expect=403)


# --- Twilio webhook ---
def test_twilio_webhook_unsigned():
    r = requests.post(f"{API}/sms/twilio-webhook", data={"From": "+14165550199", "Body": "STOP"}, timeout=30)
    assert r.status_code == 403
    r = requests.post(f"{API}/sms/twilio-webhook", data={"From": "+14165550199", "Body": "STOP"},
                      headers={"X-Twilio-Signature": "bogus"}, timeout=30)
    assert r.status_code == 403
