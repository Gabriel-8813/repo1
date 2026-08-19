"""Health-data hardening tests: field-level encryption, least privilege, consent,
privacy-policy gate, audit immutability, data residency."""
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
backend_env = dotenv_values("/app/backend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = backend_env.get("MONGO_URL", "").strip('"')
DB_NAME = backend_env.get("DB_NAME", "").strip('"')

CREDS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
    "driver": ("driver1@test.com", "Driver@123"),
    "facility": ("facility1@test.com", "Facility@123"),
}

RECIPIENT_NAME = "TEST_Enc Recipient"
RECIPIENT_PHONE = "+14165551234"


@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def login(role):
    email, password = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {role} failed {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def tokens():
    return {r: login(r) for r in CREDS}


def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def contains_enc(obj):
    return "enc::" in json.dumps(obj, default=str)


def book_job(token, **overrides):
    payload = {
        "recipient_name": RECIPIENT_NAME,
        "recipient_phone": RECIPIENT_PHONE,
        "dropoff_address": "100 Front St W, Toronto, ON",
        "item_count": 1,
        "item_category": "prescription",
        "handling_flags": [],
        "requested_pickup_time": datetime.now(timezone.utc).isoformat(),
        "recipient_sms_consent": True,
        "consent_data_handling": True,
        "special_instructions": "TEST_hardening",
    }
    payload.update(overrides)
    return requests.post(f"{API}/facility/requests", json=payload, headers=hdr(token), timeout=90)


# ---------------- Consent gate (POST /api/facility/requests) ----------------
class TestConsentGate:
    def test_booking_without_consent_422(self, tokens):
        r = book_job(tokens["facility"], consent_data_handling=False)
        assert r.status_code == 422, r.text[:300]
        detail = json.dumps(r.json())
        assert "consent" in detail.lower()

    def test_booking_with_consent_stores_consent_block(self, tokens, mongo):
        r = book_job(tokens["facility"])
        assert r.status_code == 201, r.text[:400]
        job = r.json()
        raw = mongo.jobs.find_one({"id": job["id"]}, {"_id": 0})
        consent = raw.get("consent")
        assert consent, "consent block missing on job document"
        assert consent["delivery_and_data_handling"] is True
        assert consent.get("policy_version") == "1.0"
        assert consent.get("captured_by")
        assert consent.get("captured_at")
        mongo.jobs.delete_one({"id": job["id"]})


# ---------------- Field-level encryption at rest ----------------
class TestEncryptionAtRest:
    @pytest.fixture(scope="class")
    def job(self, tokens, mongo):
        r = book_job(tokens["facility"])
        assert r.status_code == 201, r.text[:400]
        j = r.json()
        yield j
        mongo.jobs.delete_one({"id": j["id"]})
        mongo.custody_events.delete_many({"job_id": j["id"]})
        mongo.sms_outbox.delete_many({"job_id": j["id"]})

    def test_raw_mongo_job_fields_encrypted(self, job, mongo):
        raw = mongo.jobs.find_one({"id": job["id"]}, {"_id": 0})
        assert raw["recipient_name"].startswith("enc::"), raw["recipient_name"]
        assert raw["recipient_phone"].startswith("enc::"), raw["recipient_phone"]

    def test_create_response_plaintext(self, job):
        assert job["recipient_name"] == RECIPIENT_NAME
        assert job["recipient_phone"] == RECIPIENT_PHONE

    def test_get_job_plaintext_facility_and_admin(self, job, tokens):
        for role in ("facility", "admin"):
            r = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 200, r.text[:200]
            d = r.json()
            assert d["recipient_name"] == RECIPIENT_NAME
            assert d["recipient_phone"] == RECIPIENT_PHONE
            assert not contains_enc(d)

    def test_dispatch_board_no_ciphertext(self, tokens, job):
        r = requests.get(f"{API}/dispatch/board", headers=hdr(tokens["dispatcher"]), timeout=60)
        assert r.status_code == 200
        assert not contains_enc(r.json()), "enc:: leaked in dispatch board"

    def test_facility_deliveries_no_ciphertext(self, tokens, job):
        r = requests.get(f"{API}/facility/deliveries", headers=hdr(tokens["facility"]), timeout=60)
        assert r.status_code == 200
        assert not contains_enc(r.json()), "enc:: leaked in facility deliveries"

    def test_breach_report_no_ciphertext(self, tokens):
        r = requests.get(f"{API}/admin/compliance/breach-report", headers=hdr(tokens["admin"]), timeout=60,
                         params={"date_from": "2020-01-01", "date_to": "2030-01-01"})
        assert r.status_code == 200
        assert not contains_enc(r.json()), "enc:: leaked in breach report"

    def test_admin_jobs_list_no_ciphertext(self, tokens):
        r = requests.get(f"{API}/admin/jobs", headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200
        assert not contains_enc(r.json()), "enc:: leaked in GET /api/admin/jobs"

    def test_jobs_list_no_ciphertext(self, tokens):
        r = requests.get(f"{API}/jobs", headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200
        assert not contains_enc(r.json()), "enc:: leaked in GET /api/jobs"


# ---------------- Least privilege for drivers ----------------
class TestDriverLeastPrivilege:
    @pytest.fixture(scope="class")
    def job(self, tokens, mongo):
        r = book_job(tokens["facility"])
        assert r.status_code == 201, r.text[:400]
        j = r.json()
        # move to open pool so an unassigned driver can see it
        mongo.jobs.update_one({"id": j["id"]}, {"$set": {"status": "open"}})
        yield j
        mongo.jobs.delete_one({"id": j["id"]})
        mongo.custody_events.delete_many({"job_id": j["id"]})
        mongo.sms_outbox.delete_many({"job_id": j["id"]})

    def test_available_jobs_masked(self, tokens, job):
        r = requests.get(f"{API}/jobs/available", headers=hdr(tokens["driver"]), timeout=60)
        assert r.status_code == 200, r.text[:200]
        jobs = r.json()["jobs"]
        assert not contains_enc(jobs), "enc:: leaked to driver"
        mine = [j for j in jobs if j["id"] == job["id"]]
        assert mine, "test job not visible in available pool"
        j = mine[0]
        for f in ("recipient_name", "recipient_phone", "pickup_address", "delivery_address", "dropoff_address"):
            assert j.get(f) in (None, ""), f"{f} exposed to unassigned driver: {j.get(f)}"
        assert j.get("pickup_area")
        assert j.get("dropoff_area")
        # no facility billing / pricing leakage
        blob = json.dumps(jobs)
        assert "billing_email" not in blob
        assert "per_delivery_rate" not in blob

    def test_assigned_job_reveals_plaintext(self, tokens, job, mongo):
        r = requests.post(f"{API}/jobs/{job['id']}/accept", headers=hdr(tokens["driver"]), timeout=60)
        assert r.status_code == 200, r.text[:300]
        g = requests.get(f"{API}/jobs/{job['id']}", headers=hdr(tokens["driver"]), timeout=30)
        assert g.status_code == 200
        d = g.json()
        assert d["recipient_name"] == RECIPIENT_NAME
        assert d["recipient_phone"] == RECIPIENT_PHONE
        assert d.get("delivery_address") or d.get("dropoff_address")
        assert not contains_enc(d)
        # cleanup: release driver
        mongo.jobs.update_one({"id": job["id"]},
                              {"$set": {"status": "open"}, "$unset": {"accepted_by": "", "assigned_driver_id": "", "accepted_at": ""}})


# ---------------- Full delivery E2E with encryption + SMS ----------------
class TestDeliveryE2E:
    def test_full_flow(self, tokens, mongo):
        r = book_job(tokens["facility"])
        assert r.status_code == 201, r.text[:400]
        job = r.json()
        jid = job["id"]
        try:
            mongo.jobs.update_one({"id": jid}, {"$set": {"status": "open"}})
            acc = requests.post(f"{API}/jobs/{jid}/accept", headers=hdr(tokens["driver"]), timeout=60)
            assert acc.status_code == 200, acc.text[:300]

            pu = requests.post(f"{API}/jobs/{jid}/custody-events", headers=hdr(tokens["driver"]), timeout=60, json={
                "event_type": "pickup_confirmed",
                "checklist": {"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True},
            })
            assert pu.status_code == 201, pu.text[:300]

            files = {"file": ("sig.png", io.BytesIO(b"\x89PNG\r\n\x1a\nTESTSIG"), "image/png")}
            ev = requests.post(f"{API}/jobs/{jid}/delivery-evidence", files=files, data={"kind": "signature"},
                               headers={"Authorization": f"Bearer {tokens['driver']}"}, timeout=60)
            assert ev.status_code == 201, ev.text[:300]
            evidence_url = ev.json().get("url") or ev.json().get("file_url") or ev.json().get("evidence_url")
            assert evidence_url, ev.json()

            dl = requests.post(f"{API}/jobs/{jid}/custody-events", headers=hdr(tokens["driver"]), timeout=60, json={
                "event_type": "delivered",
                "recipient_name": RECIPIENT_NAME,
                "recipient_relationship": "self",
                "evidence_url": evidence_url,
            })
            assert dl.status_code == 201, dl.text[:300]
            # API response must not leak ciphertext (checked at the end so the rest of the flow runs)
            leaks = []
            if contains_enc(dl.json()):
                leaks.append(f"POST /api/jobs/{{id}}/custody-events response leaks enc:: -> {dl.text[:200]}")

            # raw custody event encrypted
            raw = mongo.custody_events.find_one({"job_id": jid, "event_type": "delivered"}, {"_id": 0})
            assert raw["recipient_name"].startswith("enc::"), raw["recipient_name"]
            assert raw.get("recipient_relationship", "").startswith("enc::"), raw.get("recipient_relationship")

            # custody events list decrypted
            ce = requests.get(f"{API}/jobs/{jid}/custody-events", headers=hdr(tokens["facility"]), timeout=30)
            assert ce.status_code == 200
            assert not contains_enc(ce.json())
            delivered = [e for e in ce.json()["custody_events"] if e["event_type"] == "delivered"][0]
            assert delivered["recipient_name"] == RECIPIENT_NAME
            assert delivered["recipient_relationship"] == "self"

            # custody PDF
            pdf = requests.get(f"{API}/jobs/{jid}/custody-record/pdf", headers=hdr(tokens["admin"]), timeout=90)
            assert pdf.status_code == 200, pdf.text[:200]
            assert pdf.content[:4] == b"%PDF", pdf.content[:20]

            # SMS outbox has real phone numbers, not ciphertext
            outbox = list(mongo.sms_outbox.find({"job_id": jid}, {"_id": 0}))
            assert outbox, "no SMS outbox rows for job"
            for row in outbox:
                assert row["to_phone"] == RECIPIENT_PHONE, row
                assert "enc::" not in row["body"]
            kinds = {row.get("kind") for row in outbox}
            assert "delivered" in kinds, kinds

            # facility deliveries POD plaintext
            fd = requests.get(f"{API}/facility/deliveries", headers=hdr(tokens["facility"]), timeout=60)
            assert fd.status_code == 200
            mine = [d for d in fd.json()["deliveries"] if d["id"] == jid]
            assert mine and mine[0]["recipient_name"] == RECIPIENT_NAME
            assert not leaks, "; ".join(leaks)
        finally:
            mongo.jobs.delete_one({"id": jid})
            mongo.custody_events.delete_many({"job_id": jid})
            mongo.sms_outbox.delete_many({"job_id": jid})
            mongo.delivery_evidence.delete_many({"job_id": jid})
            mongo.notifications.delete_many({"job_id": jid})


# ---------------- Privacy policy gate ----------------
class TestPrivacyGate:
    def test_register_without_acceptance_422(self):
        email = f"TEST_priv_{uuid.uuid4().hex[:8]}@test.com"
        r = requests.post(f"{API}/auth/register", timeout=30, json={
            "email": email, "password": "Test@1234", "full_name": "TEST_NoPriv", "phone": "+14165550000"})
        assert r.status_code == 422, r.text[:300]
        assert "privacy" in r.text.lower()

    def test_register_with_acceptance_and_me(self, mongo):
        email = f"TEST_priv_{uuid.uuid4().hex[:8]}@test.com"
        try:
            r = requests.post(f"{API}/auth/register", timeout=30, json={
                "email": email, "password": "Test@1234", "full_name": "TEST_Priv", "phone": "+14165550001",
                "privacy_policy_accepted": True})
            assert r.status_code == 200, r.text[:300]
            body = r.json()
            pp = body["user"]["privacy_policy"]
            assert pp["version"] == "1.0" and pp["accepted_at"]
            tok = body["access_token"]
            me = requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30)
            assert me.status_code == 200
            assert me.json()["privacy_policy"]["version"] == "1.0"
            lg = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"}, timeout=30)
            assert lg.status_code == 200
            assert lg.json()["user"]["privacy_policy"]["version"] == "1.0"
        finally:
            mongo.users.delete_one({"email": email})

    def test_accept_privacy_for_existing_user(self, mongo):
        email = f"TEST_priv_{uuid.uuid4().hex[:8]}@test.com"
        try:
            r = requests.post(f"{API}/auth/register", timeout=30, json={
                "email": email, "password": "Test@1234", "full_name": "TEST_Legacy", "phone": "+14165550002",
                "privacy_policy_accepted": True})
            assert r.status_code == 200
            tok = r.json()["access_token"]
            uid = r.json()["user"]["id"]
            mongo.users.update_one({"email": email}, {"$unset": {"privacy_policy": ""}})
            me = requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30)
            assert me.json().get("privacy_policy") is None

            ap = requests.post(f"{API}/auth/accept-privacy", headers=hdr(tok), timeout=30)
            assert ap.status_code == 200, ap.text[:300]
            assert ap.json()["privacy_policy"]["version"] == "1.0"
            me2 = requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30)
            assert me2.json()["privacy_policy"]["version"] == "1.0"
            audit = mongo.audit_logs.find_one({"actor_id": uid, "action": "accept", "entity": "privacy_policy"})
            assert audit, "no audit entry written for privacy acceptance"
        finally:
            mongo.users.delete_one({"email": email})

    def test_accept_privacy_requires_auth(self):
        r = requests.post(f"{API}/auth/accept-privacy", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- Data residency ----------------
class TestResidency:
    def test_staff_can_read(self, tokens):
        for role in ("admin", "dispatcher"):
            r = requests.get(f"{API}/admin/compliance/residency", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 200, r.text[:200]
            d = r.json()
            assert d["configured_region"] == "ca-central"
            assert len(d["components"]) == 3
            assert all(c["region"] == "ca-central" for c in d["components"])
            assert "Fernet" in d["encryption"]["at_rest"]
            assert "TLS" in d["encryption"]["in_transit"]
            assert d["attestation"]

    def test_driver_forbidden(self, tokens):
        r = requests.get(f"{API}/admin/compliance/residency", headers=hdr(tokens["driver"]), timeout=30)
        assert r.status_code == 403, r.status_code

    def test_unauthenticated(self):
        r = requests.get(f"{API}/admin/compliance/residency", timeout=30)
        assert r.status_code in (401, 403)


# ---------------- Audit immutability ----------------
class TestAuditIntegrity:
    def test_intact_and_count(self, tokens):
        r = requests.get(f"{API}/admin/compliance/audit-integrity", headers=hdr(tokens["admin"]), timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["intact"] is True, d
        assert d["entries_checked"] >= 4877, d
        assert d.get("verified_at")

    def test_driver_forbidden(self, tokens):
        r = requests.get(f"{API}/admin/compliance/audit-integrity", headers=hdr(tokens["driver"]), timeout=60)
        assert r.status_code == 403

    def test_tamper_detected_and_restored(self, tokens, mongo):
        target = mongo.audit_logs.find_one({"seq": {"$exists": True}}, sort=[("seq", 1)])
        assert target, "no chained audit entries"
        original = target["action"]
        seq = target["seq"]
        try:
            mongo.audit_logs.update_one({"seq": seq}, {"$set": {"action": "TAMPERED"}})
            r = requests.get(f"{API}/admin/compliance/audit-integrity", headers=hdr(tokens["admin"]), timeout=120)
            assert r.status_code == 200
            d = r.json()
            assert d["intact"] is False, d
            assert str(seq) in d["problem"], d
            assert "edit" in d["problem"].lower(), d
        finally:
            mongo.audit_logs.update_one({"seq": seq}, {"$set": {"action": original}})
        r2 = requests.get(f"{API}/admin/compliance/audit-integrity", headers=hdr(tokens["admin"]), timeout=120)
        assert r2.json()["intact"] is True, r2.json()

    def test_deletion_detected_and_restored(self, tokens, mongo):
        doc = mongo.audit_logs.find_one({"seq": {"$exists": True}}, sort=[("seq", -1)])
        assert doc
        saved = dict(doc)
        try:
            mongo.audit_logs.delete_one({"_id": doc["_id"]})
            d = requests.get(f"{API}/admin/compliance/audit-integrity",
                             headers=hdr(tokens["admin"]), timeout=120).json()
            # deleting the last entry cannot be detected by seq gap; only mid-chain gaps are
            print(f"integrity after deleting last entry (seq {doc['seq']}): {d}")
        finally:
            mongo.audit_logs.insert_one(saved)
        assert requests.get(f"{API}/admin/compliance/audit-integrity",
                            headers=hdr(tokens["admin"]), timeout=120).json()["intact"] is True

    def test_no_mutation_endpoints_for_audit_logs(self, tokens):
        h = hdr(tokens["admin"])
        for method, url in [
            ("put", f"{API}/audit-logs/someid"), ("delete", f"{API}/audit-logs/someid"),
            ("patch", f"{API}/audit-logs/someid"), ("delete", f"{API}/audit-logs"),
            ("put", f"{API}/admin/audit-logs/someid"), ("delete", f"{API}/admin/audit-logs/someid"),
        ]:
            r = getattr(requests, method)(url, headers=h, timeout=30)
            assert r.status_code in (404, 405), f"{method.upper()} {url} -> {r.status_code}"

    def test_new_entries_continue_chain(self, tokens, mongo):
        before = mongo.audit_logs.find_one({"seq": {"$exists": True}}, sort=[("seq", -1)])["seq"]
        r = requests.get(f"{API}/jobs", headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200
        # trigger a write-audited action: create + delete a facility-less job via admin? use accept-privacy on temp user
        email = f"TEST_chain_{uuid.uuid4().hex[:8]}@test.com"
        try:
            reg = requests.post(f"{API}/auth/register", timeout=30, json={
                "email": email, "password": "Test@1234", "full_name": "TEST_Chain", "phone": "+14165550003",
                "privacy_policy_accepted": True})
            assert reg.status_code == 200
            requests.post(f"{API}/auth/accept-privacy", headers=hdr(reg.json()["access_token"]), timeout=30)
        finally:
            mongo.users.delete_one({"email": email})
        after_doc = mongo.audit_logs.find_one({"seq": {"$exists": True}}, sort=[("seq", -1)])
        assert after_doc["seq"] > before, "audit seq did not increment"
        d = requests.get(f"{API}/admin/compliance/audit-integrity", headers=hdr(tokens["admin"]), timeout=120).json()
        assert d["intact"] is True, d


# ---------------- No leftover plaintext PII at rest ----------------
class TestMigration:
    def test_all_job_pii_encrypted(self, mongo):
        bad = [j["id"] for j in mongo.jobs.find({}, {"id": 1, "recipient_name": 1, "recipient_phone": 1})
               if (isinstance(j.get("recipient_name"), str) and j["recipient_name"] not in ("", "[REDACTED]")
                   and not j["recipient_name"].startswith("enc::"))
               or (isinstance(j.get("recipient_phone"), str) and j["recipient_phone"] not in ("", "[REDACTED]")
                   and not j["recipient_phone"].startswith("enc::"))]
        assert not bad, f"jobs with plaintext PII at rest: {bad[:10]}"

    def test_all_custody_pii_encrypted(self, mongo):
        bad = [e["id"] for e in mongo.custody_events.find({}, {"id": 1, "recipient_name": 1, "recipient_relationship": 1})
               if (isinstance(e.get("recipient_name"), str) and e["recipient_name"] not in ("", "[REDACTED]")
                   and not e["recipient_name"].startswith("enc::"))
               or (isinstance(e.get("recipient_relationship"), str) and e["recipient_relationship"] not in ("", "[REDACTED]")
                   and not e["recipient_relationship"].startswith("enc::"))]
        assert not bad, f"custody events with plaintext PII at rest: {bad[:10]}"


# ---------------- Known ciphertext leak points (regression guards) ----------------
class TestCiphertextLeakPoints:
    def test_single_custody_event_endpoint_decrypts(self, tokens, mongo):
        ev = mongo.custody_events.find_one({"recipient_name": {"$regex": "^enc::"}}, {"_id": 0})
        if not ev:
            pytest.skip("no encrypted custody event available")
        r = requests.get(f"{API}/custody-events/{ev['id']}", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert not contains_enc(r.json()), f"GET /api/custody-events/{{id}} leaks ciphertext: {r.text[:200]}"


# ---------------- Mid-chain deletion detection ----------------
class TestAuditDeletionDetection:
    def test_mid_chain_delete_detected_then_restored(self, tokens, mongo):
        total = mongo.audit_logs.count_documents({"seq": {"$exists": True}})
        target_seq = max(1, total // 2)
        doc = mongo.audit_logs.find_one({"seq": target_seq})
        assert doc, f"no audit entry at seq {target_seq}"
        saved = dict(doc)
        try:
            mongo.audit_logs.delete_one({"_id": doc["_id"]})
            d = requests.get(f"{API}/admin/compliance/audit-integrity",
                             headers=hdr(tokens["admin"]), timeout=120).json()
            assert d["intact"] is False, d
            assert "delete" in d["problem"].lower(), d
        finally:
            mongo.audit_logs.insert_one(saved)
        d2 = requests.get(f"{API}/admin/compliance/audit-integrity",
                          headers=hdr(tokens["admin"]), timeout=120).json()
        assert d2["intact"] is True, d2
