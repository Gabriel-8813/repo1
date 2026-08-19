"""Driver onboarding: documents upload, file serving, staff review endpoints, audit trail."""
import io
import os
import time
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

ADMIN = ("gabrielosmanhamza@yahoo.com", "Admin@123")
DRIVER1 = ("driver1@test.com", "Driver@123")
FACILITY = ("facility1@test.com", "Facility@123")
DISPATCHER = ("dispatcher1@test.com", "Dispatch@123")

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)

REQUIRED = [
    "drivers_licence",
    "vehicle_registration",
    "cvor",
    "tdg_certificate",
    "vulnerable_sector_check",
    "commercial_insurance",
]


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def dispatcher_token():
    return login(*DISPATCHER)


@pytest.fixture(scope="module")
def facility_token():
    return login(*FACILITY)


@pytest.fixture(scope="module")
def driver1_token():
    return login(*DRIVER1)


@pytest.fixture(scope="module")
def fresh_driver(admin_token):
    """Register a throwaway driver; delete via admin at teardown."""
    email = f"TEST_qa_{uuid.uuid4().hex[:8]}@test.com"
    pwd = "QaDriver@123"
    r = requests.post(f"{API}/auth/register", json={ "privacy_policy_accepted": True,
        "email": email, "password": pwd, "full_name": "TEST_QA Driver",
        "role": "driver", "phone": "6470000000"
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    token = body.get("access_token")
    user_id = (body.get("user") or {}).get("id")
    assert token and user_id
    yield {"email": email, "password": pwd, "token": token, "user_id": user_id}
    requests.delete(f"{API}/users/{user_id}", headers=hdr(admin_token), timeout=30)


@pytest.fixture
def open_job(facility_token):
    """Ensure an open job exists; create one as facility."""
    r = requests.post(f"{API}/jobs", headers=hdr(facility_token), json={
        "title": "TEST_QA Transport",
        "pickup_address": "1 QA St, Toronto",
        "delivery_address": "2 QA Ave, Toronto",
        "pickup_city": "Toronto",
        "delivery_city": "Toronto",
        "goods_type": "lab_specimen",
        "urgency": "standard",
        "estimated_distance_km": 12.5,
        "offered_price": 80.0,
    }, timeout=30)
    assert r.status_code in (200, 201), f"job create failed: {r.status_code} {r.text[:300]}"
    job = r.json()
    yield job


class TestOnboardingState:
    def test_new_driver_onboarding_initial(self, fresh_driver):
        r = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["verification_status"] == "incomplete"
        assert d["all_required_submitted"] is False
        assert len(d["checklist"]) == 7
        req = [c for c in d["checklist"] if c["required"]]
        assert len(req) == 6
        assert all(c["status"] == "missing" for c in d["checklist"])
        assert any(c["doc_type"] == "cold_chain_cert" and not c["required"] for c in d["checklist"])

    def test_auth_me_returns_verification_status(self, fresh_driver):
        r = requests.get(f"{API}/auth/me", headers=hdr(fresh_driver["token"]), timeout=30)
        assert r.status_code == 200
        assert r.json().get("verification_status") == "incomplete"

    def test_unverified_driver_cannot_accept_job(self, fresh_driver, open_job):
        r = requests.post(f"{API}/jobs/{open_job['id']}/accept", headers=hdr(fresh_driver["token"]), timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_onboarding_forbidden_for_facility(self, facility_token):
        r = requests.get(f"{API}/driver/onboarding", headers=hdr(facility_token), timeout=30)
        assert r.status_code == 403


class TestUploadValidation:
    def test_invalid_doc_type_422(self, fresh_driver):
        r = requests.post(f"{API}/driver/documents/not_a_doc", headers=hdr(fresh_driver["token"]),
                          files={"file": ("a.png", PNG, "image/png")}, timeout=60)
        assert r.status_code == 422, r.text[:200]

    def test_disallowed_mime_422(self, fresh_driver):
        r = requests.post(f"{API}/driver/documents/cvor", headers=hdr(fresh_driver["token"]),
                          files={"file": ("a.zip", b"PK\x03\x04zip", "application/zip")}, timeout=60)
        assert r.status_code == 422, r.text[:200]

    def test_insurance_requires_expiry_422(self, fresh_driver):
        r = requests.post(f"{API}/driver/documents/commercial_insurance", headers=hdr(fresh_driver["token"]),
                          files={"file": ("i.png", PNG, "image/png")}, timeout=60)
        assert r.status_code == 422, r.text[:200]

    def test_upload_requires_driver_role(self, facility_token):
        r = requests.post(f"{API}/driver/documents/cvor", headers=hdr(facility_token),
                          files={"file": ("a.png", PNG, "image/png")}, timeout=60)
        assert r.status_code == 403


class TestLifecycle:
    def test_upload_all_required_moves_to_pending_review(self, fresh_driver):
        token = fresh_driver["token"]
        for dt in REQUIRED:
            data = {"insurance_expiry": "2027-01-31"} if dt == "commercial_insurance" else {}
            if dt == "vehicle_registration":
                data["vehicle_plate"] = "TESTQA1"
            r = requests.post(f"{API}/driver/documents/{dt}", headers=hdr(token),
                              files={"file": (f"{dt}.png", PNG, "image/png")}, data=data, timeout=90)
            assert r.status_code == 201, f"{dt}: {r.status_code} {r.text[:300]}"
            body = r.json()
            assert body["status"] == "pending"
            assert body["doc_type"] == dt
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(token), timeout=30).json()
        assert o["all_required_submitted"] is True
        assert o["verification_status"] == "pending_review", o["verification_status"]
        statuses = {c["doc_type"]: c["status"] for c in o["checklist"]}
        for dt in REQUIRED:
            assert statuses[dt] == "pending"
        ins = [c for c in o["checklist"] if c["doc_type"] == "commercial_insurance"][0]
        assert ins["insurance_expiry"] == "2027-01-31"

    def test_file_roundtrip_owner_and_auth_query(self, fresh_driver, admin_token, facility_token, driver1_token):
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        doc_id = [c for c in o["checklist"] if c["doc_type"] == "cvor"][0]["doc_id"]
        assert doc_id
        # owner via header
        r = requests.get(f"{API}/driver-documents/{doc_id}/file", headers=hdr(fresh_driver["token"]), timeout=60)
        assert r.status_code == 200 and r.content == PNG
        # staff via ?auth= query (used by admin UI)
        r = requests.get(f"{API}/driver-documents/{doc_id}/file", params={"auth": admin_token}, timeout=60)
        assert r.status_code == 200 and r.content == PNG
        # bad token
        r = requests.get(f"{API}/driver-documents/{doc_id}/file", params={"auth": "not.a.token"}, timeout=30)
        assert r.status_code == 401
        # other driver / facility forbidden
        for t in (driver1_token, facility_token):
            r = requests.get(f"{API}/driver-documents/{doc_id}/file", headers=hdr(t), timeout=30)
            assert r.status_code == 403, r.status_code
        # unknown doc
        r = requests.get(f"{API}/driver-documents/{uuid.uuid4()}/file", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 404

    def test_dispatcher_can_review_document(self, fresh_driver, dispatcher_token):
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        doc_id = [c for c in o["checklist"] if c["doc_type"] == "tdg_certificate"][0]["doc_id"]
        r = requests.put(f"{API}/admin/driver-documents/{doc_id}",
                         json={"status": "rejected", "review_notes": "TEST_blurry scan"},
                         headers=hdr(dispatcher_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "rejected"
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        item = [c for c in o["checklist"] if c["doc_type"] == "tdg_certificate"][0]
        assert item["status"] == "rejected"
        assert item["review_notes"] == "TEST_blurry scan"
        assert o["all_required_submitted"] is False
        # re-upload replacement -> pending again
        r = requests.post(f"{API}/driver/documents/tdg_certificate", headers=hdr(fresh_driver["token"]),
                          files={"file": ("tdg2.png", PNG, "image/png")}, timeout=90)
        assert r.status_code == 201
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        assert [c for c in o["checklist"] if c["doc_type"] == "tdg_certificate"][0]["status"] == "pending"
        assert o["all_required_submitted"] is True

    def test_review_invalid_status_422(self, fresh_driver, admin_token):
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        doc_id = [c for c in o["checklist"] if c["doc_type"] == "cvor"][0]["doc_id"]
        r = requests.put(f"{API}/admin/driver-documents/{doc_id}", json={"status": "banana"},
                         headers=hdr(admin_token), timeout=30)
        assert r.status_code == 422

    def test_staff_endpoints_forbidden_for_driver_and_facility(self, fresh_driver, facility_token):
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        doc_id = [c for c in o["checklist"] if c["doc_type"] == "cvor"][0]["doc_id"]
        for t in (fresh_driver["token"], facility_token):
            r = requests.put(f"{API}/admin/driver-documents/{doc_id}", json={"status": "approved"},
                             headers=hdr(t), timeout=30)
            assert r.status_code == 403, r.status_code
            r = requests.put(f"{API}/admin/driver-verifications/{fresh_driver['user_id']}",
                             json={"verification_status": "approved"}, headers=hdr(t), timeout=30)
            assert r.status_code == 403, r.status_code
            r = requests.get(f"{API}/admin/driver-verifications", headers=hdr(t), timeout=30)
            assert r.status_code == 403, r.status_code

    def test_dispatcher_lists_verifications(self, fresh_driver, dispatcher_token):
        r = requests.get(f"{API}/admin/driver-verifications", headers=hdr(dispatcher_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        drivers = r.json()["drivers"]
        mine = [d for d in drivers if d["user_id"] == fresh_driver["user_id"]]
        assert mine, "fresh driver missing from verification list"
        assert mine[0]["email"] == fresh_driver["email"]
        assert len(mine[0]["checklist"]) == 7
        assert mine[0]["vehicle_plate"] == "TESTQA1"

    def test_dispatcher_can_set_verification_and_driver_can_accept(self, fresh_driver, dispatcher_token, open_job):
        r = requests.put(f"{API}/admin/driver-verifications/{fresh_driver['user_id']}",
                         json={"verification_status": "approved"}, headers=hdr(dispatcher_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["verification_status"] == "approved"
        o = requests.get(f"{API}/driver/onboarding", headers=hdr(fresh_driver["token"]), timeout=30).json()
        assert o["verification_status"] == "approved"
        me = requests.get(f"{API}/auth/me", headers=hdr(fresh_driver["token"]), timeout=30).json()
        assert me.get("verification_status") == "approved"
        r = requests.post(f"{API}/jobs/{open_job['id']}/accept", headers=hdr(fresh_driver["token"]), timeout=30)
        assert r.status_code == 200, f"approved driver accept failed: {r.status_code} {r.text[:300]}"

    def test_bad_verification_status_and_unknown_user(self, admin_token, fresh_driver):
        r = requests.put(f"{API}/admin/driver-verifications/{fresh_driver['user_id']}",
                         json={"verification_status": "bogus"}, headers=hdr(admin_token), timeout=30)
        assert r.status_code in (400, 422), r.status_code
        r = requests.put(f"{API}/admin/driver-verifications/{uuid.uuid4()}",
                         json={"verification_status": "approved"}, headers=hdr(admin_token), timeout=30)
        assert r.status_code == 404


class TestAuditTrail:
    def test_audit_entries_exist(self, admin_token, fresh_driver):
        r = requests.get(f"{API}/audit-logs", params={"entity": "driver_document", "limit": 500},
                         headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        logs = r.json()["logs"]
        actions = {l["action"] for l in logs}
        for a in ("upload", "view", "review"):
            assert a in actions, f"missing audit action {a}: {actions}"
        r = requests.get(f"{API}/audit-logs", params={"entity": "driver_verification", "entity_id": fresh_driver["user_id"]},
                         headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200
        vlogs = r.json()["logs"]
        assert any(l["action"] == "update" for l in vlogs), vlogs[:3]

    def test_audit_forbidden_for_driver(self, fresh_driver):
        r = requests.get(f"{API}/audit-logs", headers=hdr(fresh_driver["token"]), timeout=30)
        assert r.status_code == 403
