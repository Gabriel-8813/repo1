"""Admin Compliance feature tests: audit search, view logging, missing-POD, credential alerts,
retention/purge, chain-of-custody PDF, breach report."""
import csv
import io
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

CREDS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "facility": ("facility1@test.com", "Facility@123"),
    "driver": ("driver1@test.com", "Driver@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
}


def login(role):
    email, pwd = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {role} failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token for {role}"
    return tok


def hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def tokens():
    return {r: login(r) for r in CREDS}


@pytest.fixture(scope="session")
def ids():
    return {"user_ids": {}}


@pytest.fixture(scope="session")
def created_jobs():
    return []


@pytest.fixture(scope="session")
def driver_user_id(tokens):
    r = requests.get(f"{API}/auth/me", headers=hdr(tokens["driver"]), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return d.get("id") or d.get("user", {}).get("id")


@pytest.fixture(scope="session", autouse=True)
def cleanup(tokens, created_jobs, driver_user_id):
    yield
    a = hdr(tokens["admin"])
    # restore driver1 credentials
    requests.put(f"{API}/drivers/{driver_user_id}/record", headers=a,
                 json={"insurance_expiry": None, "verification_status": "approved"}, timeout=30)
    # restore retention
    requests.put(f"{API}/admin/compliance/retention", headers=a, json={"retention_days": 365}, timeout=30)
    for jid in list(created_jobs):
        requests.delete(f"{API}/jobs/{jid}", headers=a, timeout=30)
    try:
        db = mongo()
        ids = list(created_jobs)
        db.custody_events.delete_many({"job_id": {"$in": ids}})
        for coll in ("commission_ledger", "ledger_entries", "earnings", "driver_earnings"):
            if coll in db.list_collection_names():
                db[coll].delete_many({"job_id": {"$in": ids}})
    except Exception as e:
        print(f"cleanup warning: {e}")


_fac = {}


def facility_id(tokens):
    if "id" not in _fac:
        r = requests.get(f"{API}/facilities", headers=hdr(tokens["facility"]), timeout=30)
        assert r.status_code == 200, r.text
        _fac["id"] = r.json()["facilities"][0]["id"]
    return _fac["id"]


def create_job(tokens, created_jobs, title, price=55.0):
    payload = {
        "title": title,
        "pickup_address": "455 Queen St W, Toronto",
        "delivery_address": "100 Bloor St W, Toronto",
        "pickup_city": "Toronto",
        "delivery_city": "Mississauga",
        "goods_type": "lab_samples",
        "item_category": "lab_sample",
        "urgency": "standard",
        "estimated_distance_km": 12.0,
        "distance_km": 12.0,
        "offered_price": price,
        "payout_amount": price,
        "facility_id": facility_id(tokens),
        "recipient_name": "TEST_Recipient",
        "recipient_phone": "416-555-0000",
    }
    r = requests.post(f"{API}/jobs", headers=hdr(tokens["facility"]), json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create job {r.status_code} {r.text[:300]}"
    jid = r.json().get("id") or r.json().get("job", {}).get("id")
    assert jid
    created_jobs.append(jid)
    return jid


_db = {}


def mongo():
    if "db" not in _db:
        from pymongo import MongoClient
        be = dotenv_values("/app/backend/.env")
        _db["db"] = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
    return _db["db"]


def deliver_facility_request(tokens, created_jobs, phone="416-555-0000"):
    """Create a job through the facility portal (stores recipient PII) and drive it to delivered."""
    payload = {
        "recipient_name": "TEST_Recipient",
        "recipient_phone": phone,
        "dropoff_address": "100 Bloor St W, Toronto",
        "item_count": 1,
        "item_category": "lab_sample",
        "handling_flags": [],
        "requested_pickup_time": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "facility_id": facility_id(tokens),
    }
    r = requests.post(f"{API}/facility/requests", headers=hdr(tokens["facility"]), json=payload, timeout=30)
    assert r.status_code in (200, 201), f"facility request {r.status_code} {r.text[:300]}"
    body = r.json()
    jid = body.get("id") or body.get("job", {}).get("id") or body.get("job_id")
    assert jid, body
    created_jobs.append(jid)
    dh = hdr(tokens["driver"])
    ra = requests.post(f"{API}/jobs/{jid}/accept", headers=dh, timeout=30)
    assert ra.status_code in (200, 201), f"accept {ra.status_code} {ra.text[:300]}"
    rp = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
        "event_type": "pickup_confirmed",
        "checklist": {"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True},
        "gps_lat": 43.65, "gps_lng": -79.39}, timeout=30)
    assert rp.status_code in (200, 201), rp.text[:300]
    rd = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
        "event_type": "delivered", "recipient_name": "TEST_Recipient",
        "recipient_relationship": "self",
        "evidence_url": "https://example.com/sig.png", "gps_lat": 43.6, "gps_lng": -79.6}, timeout=30)
    assert rd.status_code in (200, 201), rd.text[:300]
    return jid


# ---------- AUDIT LOG SEARCH ----------
class TestAuditSearch:
    def test_rbac_driver_facility_forbidden(self, tokens):
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/audit-logs", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403, f"{role} -> {r.status_code}"

    def test_unauthenticated(self):
        r = requests.get(f"{API}/audit-logs", timeout=30)
        assert r.status_code in (401, 403)

    def test_enrichment_fields(self, tokens):
        r = requests.get(f"{API}/audit-logs?limit=20", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "logs" in data and "count" in data
        assert data["count"] == len(data["logs"])
        assert data["logs"], "no audit logs present"
        for log in data["logs"]:
            assert "_id" not in log
            for k in ("actor_name", "actor_email", "action", "entity", "timestamp"):
                assert k in log, f"missing {k}"

    def test_q_matches_actor_email(self, tokens):
        r = requests.get(f"{API}/audit-logs", params={"q": "dispatcher1", "limit": 50},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        logs = r.json()["logs"]
        assert logs, "q=dispatcher1 returned nothing (dispatcher must have audit history)"
        for log in logs:
            hay = f"{log.get('actor_email')} {log.get('actor_name')} {log.get('action')} {log.get('entity')} {log.get('entity_id')}".lower()
            assert "dispatcher1" in hay, log

    def test_q_plus_action_combined(self, tokens):
        r = requests.get(f"{API}/audit-logs", params={"q": "dispatcher1", "action": "update", "limit": 50},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        for log in r.json()["logs"]:
            assert log["action"] == "update"
            assert "dispatcher1" in (log.get("actor_email") or "").lower()

    def test_action_filter(self, tokens):
        r = requests.get(f"{API}/audit-logs", params={"action": "create", "limit": 30},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200
        assert all(l["action"] == "create" for l in r.json()["logs"])

    def test_entity_filter(self, tokens):
        r = requests.get(f"{API}/audit-logs", params={"entity": "job", "limit": 30},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200
        assert all(l["entity"] == "job" for l in r.json()["logs"])

    def test_date_range_inclusive(self, tokens):
        today = datetime.now(timezone.utc).date().isoformat()
        r = requests.get(f"{API}/audit-logs", params={"date_from": today, "date_to": today, "limit": 100},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        logs = r.json()["logs"]
        assert logs, "no logs today"
        for log in logs:
            assert log["timestamp"][:10] == today, log["timestamp"]

    def test_date_range_excludes_future(self, tokens):
        future = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
        r = requests.get(f"{API}/audit-logs", params={"date_from": future, "limit": 50},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200
        assert r.json()["logs"] == []


# ---------- VIEW LOGGING + DEDUPE ----------
class TestViewLogging:
    def test_job_view_logged_and_deduped(self, tokens, created_jobs):
        jid = create_job(tokens, created_jobs, "TEST_compliance_viewlog")
        dh = hdr(tokens["dispatcher"])
        a = hdr(tokens["admin"])

        r = requests.get(f"{API}/jobs/{jid}", headers=dh, timeout=30)
        assert r.status_code == 200, r.text
        logs = requests.get(f"{API}/audit-logs", params={"entity": "job", "entity_id": jid, "action": "view"},
                            headers=a, timeout=30).json()["logs"]
        assert len(logs) == 1, f"expected 1 view log, got {len(logs)}"
        assert "dispatcher1" in (logs[0]["actor_email"] or "")

        # repeat -> deduped
        requests.get(f"{API}/jobs/{jid}", headers=dh, timeout=30)
        requests.get(f"{API}/jobs/{jid}", headers=dh, timeout=30)
        logs2 = requests.get(f"{API}/audit-logs", params={"entity": "job", "entity_id": jid, "action": "view"},
                             headers=a, timeout=30).json()["logs"]
        assert len(logs2) == 1, f"dedupe failed: {len(logs2)} view logs"

    def test_custody_events_view_logged_and_deduped(self, tokens, created_jobs):
        jid = create_job(tokens, created_jobs, "TEST_compliance_custodyviewlog")
        dh = hdr(tokens["dispatcher"])
        a = hdr(tokens["admin"])
        r = requests.get(f"{API}/jobs/{jid}/custody-events", headers=dh, timeout=30)
        assert r.status_code == 200, r.text
        q = {"entity": "job_custody", "entity_id": jid, "action": "view"}
        logs = requests.get(f"{API}/audit-logs", params=q, headers=a, timeout=30).json()["logs"]
        assert len(logs) == 1, f"expected 1 job_custody view log, got {len(logs)}"
        requests.get(f"{API}/jobs/{jid}/custody-events", headers=dh, timeout=30)
        logs2 = requests.get(f"{API}/audit-logs", params=q, headers=a, timeout=30).json()["logs"]
        assert len(logs2) == 1, f"dedupe failed: {len(logs2)}"

    def test_view_logging_does_not_break_driver_job_get(self, tokens, created_jobs):
        jid = create_job(tokens, created_jobs, "TEST_compliance_driverget")
        r = requests.get(f"{API}/jobs/{jid}", headers=hdr(tokens["driver"]), timeout=30)
        assert r.status_code == 200, f"driver GET job -> {r.status_code} {r.text[:200]}"


# ---------- MISSING POD ----------
class TestMissingPod:
    def test_rbac(self, tokens):
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/admin/compliance/missing-pod", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403, f"{role} -> {r.status_code}"
        for role in ("admin", "dispatcher"):
            r = requests.get(f"{API}/admin/compliance/missing-pod", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 200, f"{role} -> {r.status_code}"

    def test_delivered_without_event_appears(self, tokens, created_jobs, driver_user_id):
        jid = create_job(tokens, created_jobs, "TEST_compliance_nopod")
        dh = hdr(tokens["dispatcher"])
        a = hdr(tokens["admin"])
        for st in ("accepted", "picked_up", "in_transit", "delivered"):
            body = {"status": st}
            if st == "accepted":
                body["assigned_driver_id"] = driver_user_id
            r = requests.put(f"{API}/jobs/{jid}", headers=dh, json=body, timeout=30)
            assert r.status_code == 200, f"{st} -> {r.status_code} {r.text[:200]}"
        rows = requests.get(f"{API}/admin/compliance/missing-pod", headers=a, timeout=30).json()["jobs"]
        row = next((x for x in rows if x["job_id"] == jid), None)
        assert row, "delivered job without POD not listed"
        assert row["issue"] == "no_delivered_event", row
        assert row["facility_name"] == "LifeLabs Queen West", row
        assert row["driver_name"], "driver_name not enriched"
        assert row["delivered_at"]

    def test_job_with_full_pod_not_listed(self, tokens, created_jobs):
        jid = create_job(tokens, created_jobs, "TEST_compliance_withpod")
        dh = hdr(tokens["driver"])
        ra = requests.post(f"{API}/jobs/{jid}/accept", headers=dh, timeout=30)
        assert ra.status_code in (200, 201), ra.text[:200]
        rp = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
            "event_type": "pickup_confirmed",
            "checklist": {"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True},
            "gps_lat": 43.65, "gps_lng": -79.39}, timeout=30)
        assert rp.status_code in (200, 201), rp.text[:200]
        rd = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
            "event_type": "delivered", "recipient_name": "TEST_Recipient",
            "evidence_url": "https://example.com/sig.png", "gps_lat": 43.6, "gps_lng": -79.6}, timeout=30)
        assert rd.status_code in (200, 201), rd.text[:200]
        rows = requests.get(f"{API}/admin/compliance/missing-pod", headers=hdr(tokens["admin"]), timeout=30).json()["jobs"]
        assert all(x["job_id"] != jid for x in rows), "job with full POD wrongly flagged"


# ---------- CREDENTIAL ALERTS ----------
class TestCredentialAlerts:
    def test_rbac(self, tokens):
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/admin/compliance/credential-alerts", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403

    def _set_expiry(self, tokens, driver_user_id, value):
        r = requests.put(f"{API}/drivers/{driver_user_id}/record", headers=hdr(tokens["admin"]),
                         json={"insurance_expiry": value}, timeout=30)
        assert r.status_code == 200, f"set expiry {value} -> {r.status_code} {r.text[:200]}"

    def _alert(self, tokens, driver_user_id):
        r = requests.get(f"{API}/admin/compliance/credential-alerts", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        return next((a for a in r.json()["alerts"] if a["user_id"] == driver_user_id), None)

    def test_expired_then_expiring_then_clear(self, tokens, driver_user_id):
        past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
        self._set_expiry(tokens, driver_user_id, past)
        al = self._alert(tokens, driver_user_id)
        assert al, "no alert for expired insurance"
        assert any(i["type"] == "insurance_expired" for i in al["issues"]), al
        assert al["email"] == CREDS["driver"][0]

        soon = (datetime.now(timezone.utc) + timedelta(days=15)).date().isoformat()
        self._set_expiry(tokens, driver_user_id, soon)
        al = self._alert(tokens, driver_user_id)
        assert al, "no alert for expiring insurance"
        assert any(i["type"] == "insurance_expiring" for i in al["issues"]), al

        far = (datetime.now(timezone.utc) + timedelta(days=200)).date().isoformat()
        self._set_expiry(tokens, driver_user_id, far)
        assert self._alert(tokens, driver_user_id) is None, "alert persists with far-future expiry"
        self._set_expiry(tokens, driver_user_id, None)
        assert self._alert(tokens, driver_user_id) is None, "alert persists after clearing expiry"


# ---------- RETENTION / PURGE ----------
class TestRetention:
    def test_rbac_non_admin(self, tokens):
        for role in ("dispatcher", "driver", "facility"):
            r = requests.get(f"{API}/admin/compliance/retention", headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403, f"{role} GET -> {r.status_code}"
            r = requests.post(f"{API}/admin/compliance/purge", headers=hdr(tokens[role]), json={}, timeout=30)
            assert r.status_code == 403, f"{role} purge -> {r.status_code}"

    def test_get_default(self, tokens):
        r = requests.get(f"{API}/admin/compliance/retention", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["retention_days"], int)
        assert 30 <= d["retention_days"] <= 3650
        assert "last_purge" in d

    def test_validation_bounds(self, tokens):
        a = hdr(tokens["admin"])
        for bad in (20, 0, -5, 4000):
            r = requests.put(f"{API}/admin/compliance/retention", headers=a, json={"retention_days": bad}, timeout=30)
            assert r.status_code == 422, f"retention_days={bad} -> {r.status_code}"

    def test_update_writes_audit(self, tokens):
        a = hdr(tokens["admin"])
        prev = requests.get(f"{API}/admin/compliance/retention", headers=a, timeout=30).json()["retention_days"]
        r = requests.put(f"{API}/admin/compliance/retention", headers=a, json={"retention_days": 30}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["retention_days"] == 30
        # persisted
        got = requests.get(f"{API}/admin/compliance/retention", headers=a, timeout=30).json()
        assert got["retention_days"] == 30
        logs = requests.get(f"{API}/audit-logs", params={"entity": "data_retention", "action": "update", "limit": 5},
                            headers=a, timeout=30).json()["logs"]
        assert logs, "no audit entry for retention update"
        assert logs[0]["details"] == {"from": prev, "to": 30}, logs[0]
        # restore
        rr = requests.put(f"{API}/admin/compliance/retention", headers=a, json={"retention_days": 365}, timeout=30)
        assert rr.status_code == 200
        assert requests.get(f"{API}/admin/compliance/retention", headers=a, timeout=30).json()["retention_days"] == 365

    def test_purge_runs_and_audits(self, tokens):
        a = hdr(tokens["admin"])
        r = requests.post(f"{API}/admin/compliance/purge", headers=a, json={}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("purged_jobs", "retention_days", "cutoff", "ran_at"):
            assert k in d, d
        assert isinstance(d["purged_jobs"], int)
        logs = requests.get(f"{API}/audit-logs", params={"entity": "data_retention", "action": "purge", "limit": 3},
                            headers=a, timeout=30).json()["logs"]
        assert logs, "no purge audit entry"
        assert logs[0]["details"]["ran_at"] == d["ran_at"], logs[0]
        assert logs[0]["actor_email"] == CREDS["admin"][0], "manual purge not attributed to admin"
        # last_purge reflected
        got = requests.get(f"{API}/admin/compliance/retention", headers=a, timeout=30).json()
        assert got["last_purge"]["ran_at"] == d["ran_at"]

    def test_old_job_redacted_recent_job_untouched(self, tokens, created_jobs):
        """Backdate a delivered job past the cutoff -> PII redacted; a fresh job must survive."""
        a = hdr(tokens["admin"])
        requests.put(f"{API}/admin/compliance/retention", headers=a, json={"retention_days": 365}, timeout=30)
        old_jid = deliver_facility_request(tokens, created_jobs, phone="416-555-0101")
        fresh_jid = deliver_facility_request(tokens, created_jobs, phone="416-555-0202")
        db = mongo()
        db.jobs.update_one({"id": old_jid}, {"$set": {
            "created_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()}})

        r = requests.post(f"{API}/admin/compliance/purge", headers=a, json={}, timeout=90)
        assert r.status_code == 200, r.text
        assert r.json()["purged_jobs"] >= 1, r.json()

        old = db.jobs.find_one({"id": old_jid}, {"_id": 0})
        assert old["recipient_name"] == "[REDACTED]", old["recipient_name"]
        assert old["recipient_phone"] == "[REDACTED]", old["recipient_phone"]
        assert old.get("data_purged") is True
        assert old.get("purged_at")
        for e in db.custody_events.find({"job_id": old_jid}, {"_id": 0}):
            assert e.get("evidence_url") is None, e
            if e.get("recipient_name") is not None:
                assert e["recipient_name"] == "[REDACTED]", e

        fresh = db.jobs.find_one({"id": fresh_jid}, {"_id": 0})
        assert fresh["recipient_name"] == "TEST_Recipient", fresh["recipient_name"]
        assert fresh["recipient_phone"] == "416-555-0202"
        assert not fresh.get("data_purged")
        ev = list(db.custody_events.find({"job_id": fresh_jid, "event_type": "delivered"}, {"_id": 0}))
        assert ev and ev[0].get("evidence_url"), "fresh job's evidence wrongly nulled"


# ---------- CUSTODY RECORD PDF ----------
class TestCustodyPdf:
    def test_pdf_for_admin_and_dispatcher(self, tokens, created_jobs):
        jid = create_job(tokens, created_jobs, "TEST_compliance_pdf")
        for role in ("admin", "dispatcher"):
            r = requests.get(f"{API}/jobs/{jid}/custody-record/pdf", params={"auth": tokens[role]}, timeout=60)
            assert r.status_code == 200, f"{role} -> {r.status_code} {r.text[:200]}"
            assert r.headers["content-type"].startswith("application/pdf"), r.headers["content-type"]
            assert "attachment" in r.headers.get("content-disposition", "")
            assert r.content[:4] == b"%PDF", r.content[:20]
            assert len(r.content) > 1000

    def test_pdf_bearer_header_also_works(self, tokens, created_jobs):
        jid = created_jobs[-1]
        r = requests.get(f"{API}/jobs/{jid}/custody-record/pdf", headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200, r.status_code
        assert r.content[:4] == b"%PDF"

    def test_pdf_forbidden_for_driver_facility(self, tokens, created_jobs):
        jid = created_jobs[-1]
        for role in ("driver", "facility"):
            r = requests.get(f"{API}/jobs/{jid}/custody-record/pdf", params={"auth": tokens[role]}, timeout=30)
            assert r.status_code == 403, f"{role} -> {r.status_code}"

    def test_pdf_bad_token_and_bogus_job(self, tokens):
        r = requests.get(f"{API}/jobs/does-not-exist/custody-record/pdf", params={"auth": tokens["admin"]}, timeout=30)
        assert r.status_code == 404, r.status_code
        r = requests.get(f"{API}/jobs/does-not-exist/custody-record/pdf", params={"auth": "garbage"}, timeout=30)
        assert r.status_code == 401, r.status_code

    def test_export_audited(self, tokens, created_jobs):
        jid = created_jobs[-1]
        a = hdr(tokens["admin"])
        requests.get(f"{API}/jobs/{jid}/custody-record/pdf", params={"auth": tokens["admin"]}, timeout=60)
        logs = requests.get(f"{API}/audit-logs", params={"entity": "job_custody_record", "entity_id": jid,
                                                         "action": "export"}, headers=a, timeout=30).json()["logs"]
        assert logs, "custody PDF export not audited"


# ---------- BREACH REPORT ----------
class TestBreachReport:
    RANGE = {"date_from": "2026-06-01", "date_to": "2026-08-31"}

    def test_rbac_admin_only(self, tokens):
        for role in ("dispatcher", "driver", "facility"):
            r = requests.get(f"{API}/admin/compliance/breach-report", params=self.RANGE,
                             headers=hdr(tokens[role]), timeout=30)
            assert r.status_code == 403, f"{role} -> {r.status_code}"

    def test_missing_params(self, tokens):
        r = requests.get(f"{API}/admin/compliance/breach-report", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 422, r.status_code

    def test_bad_date_format(self, tokens):
        r = requests.get(f"{API}/admin/compliance/breach-report",
                         params={"date_from": "2026/06/01", "date_to": "2026-08-31"},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 422, r.status_code

    def test_summary_consistency(self, tokens):
        r = requests.get(f"{API}/admin/compliance/breach-report", params=self.RANGE,
                         headers=hdr(tokens["admin"]), timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        s, recs = d["summary"], d["records"]
        assert s["affected_jobs"] == len(recs)
        assert s["jobs_with_personal_data"] == sum(1 for x in recs if x["contains_personal_data"])
        assert s["unique_recipients"] == len({x["recipient_name"] for x in recs if x["contains_personal_data"]})
        assert s["drivers_involved"] == len({x["driver_name"] for x in recs if x["driver_name"]})
        assert s["facilities_involved"] == len({x["facility_name"] for x in recs})
        for x in recs:
            assert self.RANGE["date_from"] <= x["created_at"][:10] <= self.RANGE["date_to"], x["created_at"]
            assert "contains_personal_data" in x and "data_purged" in x

    def test_csv_export_and_audit(self, tokens):
        a = hdr(tokens["admin"])
        params = dict(self.RANGE, format="csv", auth=tokens["admin"])
        r = requests.get(f"{API}/admin/compliance/breach-report", params=params, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("text/csv"), r.headers["content-type"]
        assert "attachment" in r.headers.get("content-disposition", "")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0][0].startswith("MediTrans"), rows[0]
        header_idx = next(i for i, row in enumerate(rows) if row and row[0] == "Job ID")
        json_recs = requests.get(f"{API}/admin/compliance/breach-report", params=self.RANGE,
                                 headers=a, timeout=60).json()["records"]
        assert len(rows) - header_idx - 1 == len(json_recs), (len(rows), header_idx, len(json_recs))
        logs = requests.get(f"{API}/audit-logs", params={"entity": "breach_report", "limit": 5},
                            headers=a, timeout=30).json()["logs"]
        assert logs, "breach report not audited"
        assert logs[0]["action"] in ("view", "export")
        assert any(l["action"] == "export" for l in logs), "CSV export not audited as export"

    def test_empty_range(self, tokens):
        r = requests.get(f"{API}/admin/compliance/breach-report",
                         params={"date_from": "1990-01-01", "date_to": "1990-01-31"},
                         headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["records"] == []
        assert d["summary"]["affected_jobs"] == 0


# ---------- REGRESSION ----------
class TestRegression:
    def test_staff_dashboards_load(self, tokens):
        a = hdr(tokens["admin"])
        for path in ["/dispatch/board", "/admin/users", "/admin/driver-verifications",
                     "/admin/facilities", "/admin/jobs", "/admin/stats", "/admin/ledger"]:
            r = requests.get(f"{API}{path}", headers=a, timeout=45)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_driver_active_delivery_and_available(self, tokens):
        dh = hdr(tokens["driver"])
        for path in ["/jobs/available", "/drivers/me/active-delivery"]:
            r = requests.get(f"{API}{path}", headers=dh, timeout=45)
            assert r.status_code in (200, 404), f"{path} -> {r.status_code} {r.text[:200]}"

    def test_revenue_tab_endpoints(self, tokens):
        a = hdr(tokens["admin"])
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        for p in ["summary", "invoices", "driver-statements"]:
            r = requests.get(f"{API}/admin/billing/{p}", params={"month": month}, headers=a, timeout=45)
            assert r.status_code == 200, f"{p} -> {r.status_code}"
