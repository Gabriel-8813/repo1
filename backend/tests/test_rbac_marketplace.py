"""RBAC + Marketplace endpoints tests (iteration_9)

Covers role scoping on jobs/facilities/drivers, driver verification gating,
audit-log writes and access control, marketplace PUT /jobs.
"""
import os
import time
import uuid
import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("gabrielosmanhamza@yahoo.com", "Admin@123")
DRIVER1 = ("driver1@test.com", "Driver@123")
FACILITY = ("facility1@test.com", "Facility@123")
DISPATCHER = ("dispatcher1@test.com", "Dispatch@123")


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tokens():
    return {
        "admin": _login(*ADMIN),
        "driver": _login(*DRIVER1),
        "facility": _login(*FACILITY),
        "dispatcher": _login(*DISPATCHER),
    }


@pytest.fixture(scope="module")
def fresh_driver():
    """Register a brand-new driver (no driver record => unverified)."""
    email = f"TEST_unverified_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@1234", "full_name": "TEST Unverified",
        "phone": "+14165550000"
    }, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    yield {"email": email, "token": data["access_token"], "user": data["user"]}
    # cleanup: admin deletes the user (best-effort)
    try:
        admin = _login(*ADMIN)
        requests.delete(f"{API}/admin/users/{data['user']['id']}", headers=_hdr(admin["access_token"]), timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def created_jobs(tokens):
    """Create 2 open jobs as admin, track ids for scoping tests + cleanup."""
    admin_tok = tokens["admin"]["access_token"]
    ids = []
    for i in range(2):
        payload = {
            "title": f"TEST_RBAC_job_{i}_{uuid.uuid4().hex[:6]}",
            "pickup_address": "1 Pickup St, Toronto",
            "delivery_address": "2 Delivery Ave, Toronto",
            "goods_type": "medical_supplies",
            "urgency": "standard",
            "estimated_distance_km": 10,
            "offered_price": 55.0,
        }
        r = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok), timeout=15)
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    yield ids
    # cleanup
    for jid in ids:
        try:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok), timeout=10)
        except Exception:
            pass


# ---------- Role routing (backend view: correct role in /auth/me) ----------
class TestRolesFromLogin:
    def test_admin_role(self, tokens):
        assert tokens["admin"]["user"]["role"] == "admin"

    def test_driver_role(self, tokens):
        assert tokens["driver"]["user"]["role"] == "driver"

    def test_facility_role(self, tokens):
        assert tokens["facility"]["user"]["role"] == "facility"

    def test_dispatcher_role(self, tokens):
        assert tokens["dispatcher"]["user"]["role"] == "dispatcher"


# ---------- POST /jobs role gating ----------
class TestJobCreationRBAC:
    _payload = {
        "title": "TEST_RBAC_perm",
        "pickup_address": "A",
        "delivery_address": "B",
        "goods_type": "medical_supplies",
        "urgency": "standard",
        "estimated_distance_km": 5,
        "offered_price": 30,
    }

    def test_driver_cannot_post(self, tokens):
        r = requests.post(f"{API}/jobs", json=self._payload, headers=_hdr(tokens["driver"]["access_token"]))
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("role", ["facility", "dispatcher", "admin"])
    def test_staff_and_facility_can_post(self, tokens, role):
        payload = dict(self._payload, title=f"TEST_RBAC_perm_{role}_{uuid.uuid4().hex[:6]}")
        tok = tokens[role]["access_token"]
        r = requests.post(f"{API}/jobs", json=payload, headers=_hdr(tok))
        assert r.status_code == 200, r.text
        jid = r.json()["id"]
        # cleanup
        requests.delete(f"{API}/jobs/{jid}", headers=_hdr(tokens["admin"]["access_token"]))


# ---------- GET /jobs scoping + logistics whitelist ----------
class TestJobListScoping:
    def test_driver_sees_open_only_and_no_posted_by(self, tokens, created_jobs):
        tok = tokens["driver"]["access_token"]
        r = requests.get(f"{API}/jobs", headers=_hdr(tok))
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert len(jobs) >= 1
        for j in jobs:
            assert "posted_by" not in j, f"driver saw posted_by: {list(j.keys())}"
            # should be open OR assigned to this driver
            assert j.get("status") == "open" or j.get("accepted_by") == tokens["driver"]["user"]["id"] \
                   or j.get("assigned_driver_id") == tokens["driver"]["user"]["id"]

    def test_admin_sees_all(self, tokens, created_jobs):
        tok = tokens["admin"]["access_token"]
        r = requests.get(f"{API}/jobs", headers=_hdr(tok))
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        for jid in created_jobs:
            assert jid in ids

    def test_dispatcher_sees_all(self, tokens, created_jobs):
        tok = tokens["dispatcher"]["access_token"]
        r = requests.get(f"{API}/jobs", headers=_hdr(tok))
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        for jid in created_jobs:
            assert jid in ids
        # dispatcher (staff) sees full job (posted_by present)
        assert any("posted_by" in j for j in r.json()["jobs"])

    def test_facility_sees_only_own(self, tokens):
        # facility1 posts a job; verify it appears; admin's jobs should NOT be in list
        fac_tok = tokens["facility"]["access_token"]
        payload = {
            "title": f"TEST_FAC_own_{uuid.uuid4().hex[:6]}",
            "pickup_address": "F1", "delivery_address": "F2",
            "goods_type": "medical_supplies", "urgency": "standard",
            "estimated_distance_km": 3, "offered_price": 20,
        }
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(fac_tok))
        assert cr.status_code == 200, cr.text
        fac_job_id = cr.json()["id"]
        try:
            r = requests.get(f"{API}/jobs", headers=_hdr(fac_tok))
            assert r.status_code == 200
            ids = [j["id"] for j in r.json()["jobs"]]
            assert fac_job_id in ids
            # facility should NOT see admin-posted TEST_RBAC jobs
            posted_by_vals = {j.get("posted_by") for j in r.json()["jobs"]}
            assert posted_by_vals == {tokens["facility"]["user"]["id"]} or \
                   all(pb == tokens["facility"]["user"]["id"] for pb in posted_by_vals if pb)
        finally:
            requests.delete(f"{API}/jobs/{fac_job_id}", headers=_hdr(tokens["admin"]["access_token"]))


# ---------- Driver verification gating on accept ----------
class TestDriverVerification:
    def test_unverified_driver_403_on_accept(self, tokens, fresh_driver, created_jobs):
        # Pick an open job
        r = requests.get(f"{API}/jobs/available", headers=_hdr(fresh_driver["token"]))
        assert r.status_code == 200
        open_jobs = [j for j in r.json()["jobs"] if j["status"] == "open"]
        assert open_jobs, "no open job available for test"
        jid = open_jobs[0]["id"]
        ar = requests.post(f"{API}/jobs/{jid}/accept", headers=_hdr(fresh_driver["token"]))
        assert ar.status_code == 403, ar.text
        assert "verif" in ar.json().get("detail", "").lower()

    def test_verified_driver_can_accept_and_complete(self, tokens):
        """Regression: driver1 legacy flow."""
        admin_tok = tokens["admin"]["access_token"]
        drv_tok = tokens["driver"]["access_token"]
        payload = {
            "title": f"TEST_REG_flow_{uuid.uuid4().hex[:6]}",
            "pickup_address": "P", "delivery_address": "D",
            "goods_type": "medical_supplies", "urgency": "standard",
            "estimated_distance_km": 8, "offered_price": 40,
        }
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        assert cr.status_code == 200
        jid = cr.json()["id"]
        try:
            ar = requests.post(f"{API}/jobs/{jid}/accept", headers=_hdr(drv_tok))
            assert ar.status_code == 200, ar.text
            assert ar.json()["job"]["status"] == "accepted"
            # complete → commission ledger
            comp = requests.post(f"{API}/jobs/{jid}/complete", headers=_hdr(drv_tok))
            assert comp.status_code == 200, comp.text
            assert comp.json()["commission_charged"] > 0
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))


# ---------- PUT /jobs marketplace + driver restrictions ----------
class TestJobUpdateRBAC:
    def test_put_assign_unverified_driver_returns_400(self, tokens, fresh_driver):
        admin_tok = tokens["admin"]["access_token"]
        payload = {"title": f"TEST_PUT_{uuid.uuid4().hex[:6]}", "pickup_address": "P",
                   "delivery_address": "D", "goods_type": "medical_supplies",
                   "urgency": "standard", "estimated_distance_km": 5, "offered_price": 25}
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        jid = cr.json()["id"]
        try:
            ur = requests.put(f"{API}/jobs/{jid}",
                              json={"assigned_driver_id": fresh_driver["user"]["id"]},
                              headers=_hdr(admin_tok))
            assert ur.status_code == 400, ur.text
            assert "verif" in ur.json().get("detail", "").lower()
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))

    def test_put_assign_verified_driver_syncs_accepted_by(self, tokens):
        admin_tok = tokens["admin"]["access_token"]
        drv_id = tokens["driver"]["user"]["id"]
        payload = {"title": f"TEST_PUT2_{uuid.uuid4().hex[:6]}", "pickup_address": "P",
                   "delivery_address": "D", "goods_type": "medical_supplies",
                   "urgency": "standard", "estimated_distance_km": 5, "offered_price": 25}
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        jid = cr.json()["id"]
        try:
            ur = requests.put(f"{API}/jobs/{jid}",
                              json={"assigned_driver_id": drv_id},
                              headers=_hdr(admin_tok))
            assert ur.status_code == 200, ur.text
            assert ur.json().get("assigned_driver_id") == drv_id
            # iteration_15 semantics: accepted_by is only set when the driver actually
            # accepts (or when staff sets status='accepted'); assigning alone must not set it.
            assert ur.json().get("accepted_by") in (None, "")
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))

    def test_put_offered_without_driver_returns_400(self, tokens):
        admin_tok = tokens["admin"]["access_token"]
        payload = {"title": f"TEST_PUT3_{uuid.uuid4().hex[:6]}", "pickup_address": "P",
                   "delivery_address": "D", "goods_type": "medical_supplies",
                   "urgency": "standard", "estimated_distance_km": 5, "offered_price": 25}
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        jid = cr.json()["id"]
        try:
            ur = requests.put(f"{API}/jobs/{jid}", json={"status": "offered"}, headers=_hdr(admin_tok))
            assert ur.status_code == 400, ur.text
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))

    def test_driver_put_only_status(self, tokens):
        """Driver assigned to job may only send status; other fields => 403."""
        admin_tok = tokens["admin"]["access_token"]
        drv_tok = tokens["driver"]["access_token"]
        payload = {"title": f"TEST_PUT4_{uuid.uuid4().hex[:6]}", "pickup_address": "P",
                   "delivery_address": "D", "goods_type": "medical_supplies",
                   "urgency": "standard", "estimated_distance_km": 5, "offered_price": 25}
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        jid = cr.json()["id"]
        try:
            # accept as driver so they are assigned
            ar = requests.post(f"{API}/jobs/{jid}/accept", headers=_hdr(drv_tok))
            assert ar.status_code == 200
            # driver PUT status-only should be ok
            ok = requests.put(f"{API}/jobs/{jid}", json={"status": "picked_up"}, headers=_hdr(drv_tok))
            assert ok.status_code == 200, ok.text
            # driver PUT with other field => 403
            bad = requests.put(f"{API}/jobs/{jid}", json={"payout_amount": 999}, headers=_hdr(drv_tok))
            assert bad.status_code == 403, bad.text
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))


# ---------- Audit logs ----------
class TestAuditLogs:
    def test_driver_forbidden(self, tokens):
        r = requests.get(f"{API}/audit-logs", headers=_hdr(tokens["driver"]["access_token"]))
        assert r.status_code == 403

    def test_facility_forbidden(self, tokens):
        r = requests.get(f"{API}/audit-logs", headers=_hdr(tokens["facility"]["access_token"]))
        assert r.status_code == 403

    def test_dispatcher_allowed(self, tokens):
        r = requests.get(f"{API}/audit-logs?limit=5", headers=_hdr(tokens["dispatcher"]["access_token"]))
        assert r.status_code == 200
        assert "logs" in r.json()

    def test_create_writes_audit(self, tokens):
        admin_tok = tokens["admin"]["access_token"]
        payload = {"title": f"TEST_AUDIT_{uuid.uuid4().hex[:6]}", "pickup_address": "P",
                   "delivery_address": "D", "goods_type": "medical_supplies",
                   "urgency": "standard", "estimated_distance_km": 5, "offered_price": 25}
        cr = requests.post(f"{API}/jobs", json=payload, headers=_hdr(admin_tok))
        jid = cr.json()["id"]
        try:
            time.sleep(0.3)
            r = requests.get(f"{API}/audit-logs?entity=job&entity_id={jid}",
                             headers=_hdr(admin_tok))
            assert r.status_code == 200
            logs = r.json()["logs"]
            actions = {l["action"] for l in logs}
            assert "create" in actions
            # every log has required fields
            for l in logs:
                for f in ("actor_id", "actor_role", "action", "entity", "entity_id", "timestamp"):
                    assert f in l
                assert l["entity"] == "job"
                assert l["entity_id"] == jid
        finally:
            requests.delete(f"{API}/jobs/{jid}", headers=_hdr(admin_tok))


# ---------- Facilities billing strip ----------
class TestFacilitiesRBAC:
    @pytest.fixture(scope="class")
    def facility_id(self, tokens):
        fac_tok = tokens["facility"]["access_token"]
        payload = {"name": f"TEST_FAC_{uuid.uuid4().hex[:6]}", "type": "hospital",
                   "status": "approved", "address": "1 A St", "billing_email": "bill@test.com",
                   "contact_name": "Test Contact", "contact_phone": "+14165550100"}
        r = requests.post(f"{API}/facilities", json=payload, headers=_hdr(fac_tok))
        assert r.status_code == 201, r.text
        fid = r.json()["id"]
        yield fid
        requests.delete(f"{API}/facilities/{fid}", headers=_hdr(tokens["admin"]["access_token"]))

    def test_driver_no_billing_email(self, tokens, facility_id):
        r = requests.get(f"{API}/facilities", headers=_hdr(tokens["driver"]["access_token"]))
        assert r.status_code == 200
        facs = r.json()["facilities"]
        assert len(facs) >= 1
        for f in facs:
            assert "billing_email" not in f, f

    def test_facility_sees_own_with_billing(self, tokens, facility_id):
        r = requests.get(f"{API}/facilities", headers=_hdr(tokens["facility"]["access_token"]))
        assert r.status_code == 200
        facs = r.json()["facilities"]
        assert len(facs) >= 1
        # all owned by facility user, billing_email present on our fixture facility
        our = [f for f in facs if f["id"] == facility_id]
        assert our and "billing_email" in our[0]

    def test_admin_sees_all_with_billing(self, tokens, facility_id):
        r = requests.get(f"{API}/facilities", headers=_hdr(tokens["admin"]["access_token"]))
        assert r.status_code == 200
        our = [f for f in r.json()["facilities"] if f["id"] == facility_id]
        assert our and "billing_email" in our[0]

    def test_dispatcher_sees_billing(self, tokens, facility_id):
        r = requests.get(f"{API}/facilities", headers=_hdr(tokens["dispatcher"]["access_token"]))
        assert r.status_code == 200
        our = [f for f in r.json()["facilities"] if f["id"] == facility_id]
        assert our and "billing_email" in our[0]


# ---------- GET /drivers dispatcher access ----------
class TestDriversListRBAC:
    def test_dispatcher_200(self, tokens):
        r = requests.get(f"{API}/drivers", headers=_hdr(tokens["dispatcher"]["access_token"]))
        assert r.status_code == 200
        assert "drivers" in r.json()

    def test_admin_200(self, tokens):
        r = requests.get(f"{API}/drivers", headers=_hdr(tokens["admin"]["access_token"]))
        assert r.status_code == 200

    def test_driver_403(self, tokens):
        r = requests.get(f"{API}/drivers", headers=_hdr(tokens["driver"]["access_token"]))
        assert r.status_code == 403

    def test_facility_403(self, tokens):
        r = requests.get(f"{API}/drivers", headers=_hdr(tokens["facility"]["access_token"]))
        assert r.status_code == 403
