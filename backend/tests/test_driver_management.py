"""Admin Driver Management backend tests.

Covers:
- GET /api/admin/driver-verifications enriched shape (credentials, insurance_flag, rating, trips, compliance)
- PUT /api/admin/driver-verifications/{user_id} statuses (suspended/rejected/pending_review/approved blocker)
- Audit logging of status changes (details.from / details.to) via both endpoints
- Compliance block: suspended + expired insurance block accept/assign and dispatch board approved_drivers
- expiring_soon still compliant
- Active delivery exception: suspended driver can still advance an in-progress job
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{base_url.rstrip('/')}/api"

CREDS_FILE = Path("/app/memory/test_credentials.md")

ACCOUNTS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
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
def tokens():
    assert CREDS_FILE.exists(), "missing /app/memory/test_credentials.md"
    return {k: login(e, p) for k, (e, p) in ACCOUNTS.items()}


def hdr(tokens, role):
    return {"Authorization": f"Bearer {tokens[role][0]}"}


@pytest.fixture(scope="module")
def created_jobs():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(tokens, created_jobs):
    yield
    h = hdr(tokens, "admin")
    # always restore driver1 to a compliant state
    did = tokens["driver"][1]["id"]
    requests.put(f"{API}/drivers/{did}/record", json={"verification_status": "approved"},
                 headers=h, timeout=60)
    requests.put(f"{API}/drivers/{did}/record", json={"insurance_expiry": None}, headers=h, timeout=60)
    for jid in created_jobs:
        requests.delete(f"{API}/jobs/{jid}", headers=h, timeout=60)


def set_insurance_expiry(tokens, user_id, value):
    """PUT /drivers/{id}/record ignores None values, so clear via direct field write when needed."""
    h = hdr(tokens, "admin")
    if value is None:
        # server strips None updates; use a far-future date is not equivalent -> use raw mongo-free approach:
        # send a sentinel far future date only if clearing is unsupported (asserted in test)
        return requests.put(f"{API}/drivers/{user_id}/record", json={"insurance_expiry": None}, headers=h, timeout=60)
    return requests.put(f"{API}/drivers/{user_id}/record", json={"insurance_expiry": value}, headers=h, timeout=60)


def get_verification(tokens, user_id):
    r = requests.get(f"{API}/admin/driver-verifications", headers=hdr(tokens, "admin"), timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    assert isinstance(body.get("drivers"), list)
    return next((d for d in body["drivers"] if d["user_id"] == user_id), None), body["drivers"]


def make_job(tokens, created_jobs, title="TEST_QA drivermgmt"):
    payload = {
        "title": title,
        "description": "QA driver management test job",
        "pickup_address": "455 Queen St W, Toronto, ON",
        "dropoff_address": "100 Queen St W, Toronto, ON",
        "item_category": "lab_sample",
        "recipient_name": "QA Lab",
        "recipient_phone": "416-555-0111",
        "payout_amount": 40.0,
        "distance_km": 5.0,
        "handling_flags": [],
    }
    r = requests.post(f"{API}/jobs", json=payload, headers=hdr(tokens, "dispatcher"), timeout=60)
    assert r.status_code in (200, 201), f"job create failed: {r.status_code} {r.text[:400]}"
    job = r.json()
    created_jobs.append(job["id"])
    return job


def set_status(tokens, user_id, status, role="admin"):
    return requests.put(f"{API}/admin/driver-verifications/{user_id}",
                        json={"verification_status": status}, headers=hdr(tokens, role), timeout=60)


def force_status(tokens, user_id, status):
    """Restore path that bypasses the document blocker (admin PUT /drivers/{id}/record)."""
    return requests.put(f"{API}/drivers/{user_id}/record", json={"verification_status": status},
                        headers=hdr(tokens, "admin"), timeout=60)


# ---------------- GET /api/admin/driver-verifications ----------------
class TestVerificationList:
    def test_rbac(self, tokens):
        for role in ("admin", "dispatcher"):
            r = requests.get(f"{API}/admin/driver-verifications", headers=hdr(tokens, role), timeout=60)
            assert r.status_code == 200, f"{role}: {r.status_code} {r.text[:200]}"
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/admin/driver-verifications", headers=hdr(tokens, role), timeout=60)
            assert r.status_code == 403, f"{role} should be 403, got {r.status_code}"
        assert requests.get(f"{API}/admin/driver-verifications", timeout=60).status_code in (401, 403)

    def test_enriched_shape(self, tokens):
        rec, all_drivers = get_verification(tokens, tokens["driver"][1]["id"])
        assert rec, "driver1 missing from driver-verifications"
        for key in ("cvor_status", "tdg_cert_status", "vulnerable_sector_check_status", "insurance_status",
                    "insurance_expiry", "insurance_flag", "rating_avg", "rating_count", "total_trips",
                    "compliant", "compliance_issues", "verification_status", "cold_chain_certified",
                    "checklist", "full_name", "email"):
            assert key in rec, f"missing key {key}"
        assert isinstance(rec["compliance_issues"], list)
        assert isinstance(rec["compliant"], bool)
        assert isinstance(rec["total_trips"], int)
        assert isinstance(rec["rating_count"], int)
        assert isinstance(rec["rating_avg"], (int, float))
        assert isinstance(rec["checklist"], list)
        assert all("_id" not in d for d in all_drivers)
        # driver1 is approved + compliant baseline
        assert rec["verification_status"] == "approved", f"baseline broken: {rec['verification_status']}"
        assert rec["compliant"] is True and rec["compliance_issues"] == []

    def test_unverified_driver_not_compliant(self, tokens):
        rec, _ = get_verification(tokens, tokens["newdriver"][1]["id"])
        assert rec, "newdriver missing"
        assert rec["compliant"] is False
        assert any("verification" in i for i in rec["compliance_issues"])


# ---------------- PUT status transitions + audit ----------------
class TestStatusTransitionsAndAudit:
    def audit_entries(self, tokens, user_id):
        r = requests.get(f"{API}/audit-logs", params={"entity": "driver_verification", "entity_id": user_id},
                         headers=hdr(tokens, "admin"), timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        logs = r.json().get("logs")
        assert isinstance(logs, list), f"unexpected audit response: {r.text[:200]}"
        return logs

    def test_suspend_reject_pending_and_audit(self, tokens):
        did = tokens["driver"][1]["id"]
        try:
            for status in ("suspended", "rejected", "pending_review"):
                r = set_status(tokens, did, status)
                assert r.status_code == 200, f"{status}: {r.status_code} {r.text[:300]}"
                assert r.json()["verification_status"] == status
                rec, _ = get_verification(tokens, did)
                assert rec["verification_status"] == status
                logs = self.audit_entries(tokens, did)
                assert logs, "no audit entries for driver_verification"
                latest = logs[0]
                assert latest.get("details", {}).get("to") == status, f"audit details wrong: {latest}"
                assert "from" in latest.get("details", {}), f"audit missing from: {latest}"
        finally:
            r = force_status(tokens, did, "approved")
            assert r.status_code == 200, f"restore failed: {r.status_code} {r.text[:300]}"

    def test_invalid_status_rejected(self, tokens):
        r = set_status(tokens, tokens["driver"][1]["id"], "banana")
        assert r.status_code in (400, 422), f"got {r.status_code}"

    def test_missing_driver_404(self, tokens):
        r = set_status(tokens, "no-such-driver-qa", "suspended")
        assert r.status_code == 404

    def test_approve_with_missing_docs_400(self, tokens):
        nd = tokens["newdriver"][1]["id"]
        r = set_status(tokens, nd, "approved")
        assert r.status_code == 400, f"expected 400 blocker, got {r.status_code} {r.text[:300]}"
        rec, _ = get_verification(tokens, nd)
        assert rec["verification_status"] != "approved"

    def test_suspend_has_no_document_blocker(self, tokens):
        nd = tokens["newdriver"][1]["id"]
        orig = requests.get(f"{API}/drivers/{nd}/record", headers=hdr(tokens, "admin"), timeout=60).json()
        try:
            r = set_status(tokens, nd, "suspended")
            assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
            assert r.json()["verification_status"] == "suspended"
        finally:
            set_status(tokens, nd, orig.get("verification_status", "incomplete"))

    def test_record_endpoint_audit_only_on_status_change(self, tokens):
        did = tokens["driver"][1]["id"]
        h = hdr(tokens, "admin")
        before = len(self.audit_entries(tokens, did))
        # non-status change -> no new audit entry
        r = requests.put(f"{API}/drivers/{did}/record", json={"vehicle_plate": "QA1234"}, headers=h, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(self.audit_entries(tokens, did)) == before, "audit written for non-status field change"
        # status change via record endpoint -> audit with from/to
        try:
            r = requests.put(f"{API}/drivers/{did}/record", json={"verification_status": "suspended"},
                             headers=h, timeout=60)
            assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
            logs = self.audit_entries(tokens, did)
            assert len(logs) == before + 1, f"expected 1 new audit entry, got {len(logs) - before}"
            assert logs[0]["details"] == {"from": "approved", "to": "suspended"}, logs[0].get("details")
        finally:
            requests.put(f"{API}/drivers/{did}/record", json={"verification_status": "approved"},
                         headers=h, timeout=60)


# ---------------- compliance block ----------------
class TestComplianceBlock:
    def board_approved(self, tokens):
        r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens, "dispatcher"), timeout=60)
        assert r.status_code == 200, r.text[:200]
        return {d["user_id"] for d in r.json()["approved_drivers"]}

    def test_suspended_driver_blocked_then_restored(self, tokens, created_jobs):
        did = tokens["driver"][1]["id"]
        job = make_job(tokens, created_jobs, "TEST_QA suspend block")
        try:
            assert set_status(tokens, did, "suspended").status_code == 200
            a = requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(tokens, "driver"), timeout=60)
            assert a.status_code == 403, f"suspended accept should be 403, got {a.status_code} {a.text[:300]}"
            assert "eligible" in a.json().get("detail", "").lower()
            assign = requests.put(f"{API}/jobs/{job['id']}",
                                  json={"assigned_driver_id": did, "status": "offered"},
                                  headers=hdr(tokens, "dispatcher"), timeout=60)
            assert assign.status_code == 400, f"expected 400, got {assign.status_code} {assign.text[:300]}"
            detail = assign.json().get("detail", "").lower()
            assert "compliant" in detail or "approved" in detail, detail
            assert did not in self.board_approved(tokens), "suspended driver still in board approved_drivers"
        finally:
            assert force_status(tokens, did, "approved").status_code == 200
        assert did in self.board_approved(tokens), "restored driver missing from approved_drivers"
        a = requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(tokens, "driver"), timeout=60)
        assert a.status_code == 200, f"accept after restore failed: {a.status_code} {a.text[:300]}"

    def test_expired_insurance_blocks_even_when_approved(self, tokens, created_jobs):
        did = tokens["driver"][1]["id"]
        job = make_job(tokens, created_jobs, "TEST_QA expired ins")
        h = hdr(tokens, "admin")
        try:
            r = set_insurance_expiry(tokens, did, "2025-01-01")
            assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
            rec, _ = get_verification(tokens, did)
            assert rec["verification_status"] == "approved"
            assert rec["insurance_flag"] == "expired", rec["insurance_flag"]
            assert rec["compliant"] is False
            assert "insurance expired" in rec["compliance_issues"], rec["compliance_issues"]
            a = requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(tokens, "driver"), timeout=60)
            assert a.status_code == 403, f"expected 403, got {a.status_code} {a.text[:300]}"
            assign = requests.put(f"{API}/jobs/{job['id']}",
                                  json={"assigned_driver_id": did, "status": "offered"},
                                  headers=hdr(tokens, "dispatcher"), timeout=60)
            assert assign.status_code == 400, f"expected 400, got {assign.status_code} {assign.text[:300]}"
            assert did not in self.board_approved(tokens), "expired-insurance driver in approved_drivers"
        finally:
            requests.put(f"{API}/drivers/{did}/record", json={"insurance_expiry": None}, headers=h, timeout=60)

    def test_expiring_soon_still_allowed(self, tokens, created_jobs):
        did = tokens["driver"][1]["id"]
        job = make_job(tokens, created_jobs, "TEST_QA expiring soon")
        soon = (datetime.now(timezone.utc).date() + timedelta(days=15)).isoformat()
        h = hdr(tokens, "admin")
        try:
            r = set_insurance_expiry(tokens, did, soon)
            assert r.status_code == 200, r.text[:300]
            rec, _ = get_verification(tokens, did)
            assert rec["insurance_flag"] == "expiring_soon", rec["insurance_flag"]
            assert rec["compliant"] is True, rec["compliance_issues"]
            assign = requests.put(f"{API}/jobs/{job['id']}",
                                  json={"assigned_driver_id": did, "status": "offered"},
                                  headers=hdr(tokens, "dispatcher"), timeout=60)
            assert assign.status_code == 200, f"assign blocked for expiring_soon: {assign.status_code} {assign.text[:300]}"
            a = requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(tokens, "driver"), timeout=60)
            assert a.status_code == 200, f"accept blocked for expiring_soon: {a.status_code} {a.text[:300]}"
            assert did in self.board_approved(tokens)
        finally:
            requests.put(f"{API}/drivers/{did}/record", json={"insurance_expiry": None}, headers=h, timeout=60)

    def test_insurance_expiry_can_be_cleared(self, tokens):
        """Restoration path used by every block test — must actually clear the field."""
        did = tokens["driver"][1]["id"]
        h = hdr(tokens, "admin")
        set_insurance_expiry(tokens, did, "2025-01-01")
        requests.put(f"{API}/drivers/{did}/record", json={"insurance_expiry": None}, headers=h, timeout=60)
        rec, _ = get_verification(tokens, did)
        if rec["insurance_flag"] == "expired":
            # cannot clear via API -> restore to a safe future date so the shared driver stays usable
            future = (datetime.now(timezone.utc).date() + timedelta(days=365)).isoformat()
            requests.put(f"{API}/drivers/{did}/record", json={"insurance_expiry": future}, headers=h, timeout=60)
            rec2, _ = get_verification(tokens, did)
            assert rec2["compliant"] is True
            pytest.fail("PUT /drivers/{id}/record cannot clear insurance_expiry (None values stripped); "
                        "driver1 restored with a +365d date instead")


# ---------------- active delivery exception ----------------
class TestActiveDeliveryException:
    def test_suspended_driver_can_advance_active_job(self, tokens, created_jobs):
        did = tokens["driver"][1]["id"]
        job = make_job(tokens, created_jobs, "TEST_QA active delivery")
        dh = hdr(tokens, "driver")
        a = requests.post(f"{API}/jobs/{job['id']}/accept", headers=dh, timeout=60)
        assert a.status_code == 200, f"accept failed: {a.status_code} {a.text[:300]}"
        p = requests.put(f"{API}/jobs/{job['id']}", json={"status": "picked_up"}, headers=dh, timeout=60)
        assert p.status_code == 200, f"picked_up failed: {p.status_code} {p.text[:300]}"
        try:
            assert set_status(tokens, did, "suspended").status_code == 200
            t = requests.put(f"{API}/jobs/{job['id']}", json={"status": "in_transit"}, headers=dh, timeout=60)
            assert t.status_code == 200, f"in_transit blocked for suspended driver: {t.status_code} {t.text[:300]}"
            ce = requests.post(f"{API}/jobs/{job['id']}/custody-events",
                               json={"event_type": "in_transit_ping", "notes": "TEST_QA custody"},
                               headers=dh, timeout=60)
            assert ce.status_code in (200, 201), f"custody event blocked: {ce.status_code} {ce.text[:300]}"
            d = requests.put(f"{API}/jobs/{job['id']}", json={"status": "delivered"}, headers=dh, timeout=60)
            assert d.status_code == 200, f"delivered blocked: {d.status_code} {d.text[:300]}"
            g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens, "admin"), timeout=60).json()
            assert g["status"] == "delivered"
        finally:
            assert force_status(tokens, did, "approved").status_code == 200
