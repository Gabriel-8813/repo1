"""Admin Facility Management: GET /api/admin/facilities, PUT /api/facilities/{id}
(status, per_delivery_rate, commission_rate_override), RBAC, audit, suspend block,
pricing and commission override."""
import os
import time

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
FACILITY = ("facility1@test.com", "Facility@123")
DRIVER = ("driver1@test.com", "Driver@123")
DISPATCHER = ("dispatcher1@test.com", "Dispatch@123")

PICKUP = "100 King St W, Toronto, ON"
DROPOFF = "Toronto General Hospital, Toronto, ON"


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"Login failed for {email}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token in login response: {r.json().keys()}"
    return tok


def h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def facility_token():
    return login(*FACILITY)


@pytest.fixture(scope="module")
def driver_token():
    return login(*DRIVER)


@pytest.fixture(scope="module")
def dispatcher_token():
    return login(*DISPATCHER)


@pytest.fixture(scope="module")
def fac1(admin_token):
    """facility1@test.com's facility doc (from admin listing)."""
    r = requests.get(f"{API}/admin/facilities", headers=h(admin_token), timeout=60)
    assert r.status_code == 200, r.text[:300]
    for f in r.json()["facilities"]:
        if (f.get("owner") or {}).get("email") == FACILITY[0]:
            return f
    pytest.fail("facility owned by facility1@test.com not found")


@pytest.fixture(scope="module")
def created_job_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def restore_state(admin_token, fac1, created_job_ids):
    yield
    requests.put(f"{API}/facilities/{fac1['id']}", headers=h(admin_token), json={
        "status": "approved", "per_delivery_rate": None, "commission_rate_override": None
    }, timeout=60)
    for jid in created_job_ids:
        requests.delete(f"{API}/jobs/{jid}", headers=h(admin_token), timeout=60)


# ---- GET /api/admin/facilities ----
class TestAdminFacilitiesList:
    def test_admin_can_list_with_enrichment(self, admin_token):
        r = requests.get(f"{API}/admin/facilities", headers=h(admin_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        facs = r.json()["facilities"]
        assert isinstance(facs, list) and len(facs) > 0
        f = facs[0]
        for key in ("id", "name", "type", "status", "billing_email", "volume"):
            assert key in f, f"missing {key}"
        assert "_id" not in f
        vol = f["volume"]
        for key in ("total_jobs", "delivered_jobs", "last_30d_jobs", "total_billed"):
            assert key in vol
            assert isinstance(vol[key], (int, float))
        owned = [x for x in facs if x.get("owner")]
        assert owned, "no facility has owner enrichment"
        o = owned[0]["owner"]
        assert set(["full_name", "email", "phone"]).issubset(o.keys())

    def test_dispatcher_allowed(self, dispatcher_token):
        r = requests.get(f"{API}/admin/facilities", headers=h(dispatcher_token), timeout=60)
        assert r.status_code == 200, r.text[:300]

    def test_driver_forbidden(self, driver_token):
        r = requests.get(f"{API}/admin/facilities", headers=h(driver_token), timeout=60)
        assert r.status_code == 403, r.text[:300]

    def test_facility_forbidden(self, facility_token):
        r = requests.get(f"{API}/admin/facilities", headers=h(facility_token), timeout=60)
        assert r.status_code == 403, r.text[:300]

    def test_unauthenticated(self):
        r = requests.get(f"{API}/admin/facilities", timeout=60)
        assert r.status_code in (401, 403)


# ---- PUT /api/facilities/{id} admin terms ----
class TestAdminFacilityUpdate:
    def test_set_and_clear_terms(self, admin_token, fac1):
        fid = fac1["id"]
        r = requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "per_delivery_rate": 42.5, "commission_rate_override": 0.15, "status": "approved"
        }, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["per_delivery_rate"] == 42.5
        assert d["commission_rate_override"] == 0.15
        assert d["status"] == "approved"
        assert "_id" not in d

        g = requests.get(f"{API}/facilities/{fid}", headers=h(admin_token), timeout=60).json()
        assert g["per_delivery_rate"] == 42.5 and g["commission_rate_override"] == 0.15

        r = requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "per_delivery_rate": None, "commission_rate_override": None
        }, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["per_delivery_rate"] is None
        assert r.json()["commission_rate_override"] is None
        g = requests.get(f"{API}/facilities/{fid}", headers=h(admin_token), timeout=60).json()
        assert g["per_delivery_rate"] is None and g["commission_rate_override"] is None

    def test_validation_errors(self, admin_token, fac1):
        fid = fac1["id"]
        r = requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                         json={"commission_rate_override": 1.5}, timeout=60)
        assert r.status_code == 422, r.text[:300]
        r = requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                         json={"per_delivery_rate": -5}, timeout=60)
        assert r.status_code == 422, r.text[:300]
        r = requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                         json={"status": "bogus"}, timeout=60)
        assert r.status_code in (400, 422), r.text[:300]

    def test_status_transitions_audited(self, admin_token, fac1):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"status": "suspended"}, timeout=60).status_code == 200
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"status": "approved", "per_delivery_rate": 33.0}, timeout=60).status_code == 200
        r = requests.get(f"{API}/audit-logs", headers=h(admin_token),
                         params={"entity": "facility", "entity_id": fid}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        logs = r.json()["logs"]
        assert logs, "no audit logs for facility"
        details = [l.get("details") or {} for l in logs]
        status_change = [d for d in details if "status" in d]
        assert status_change, f"no status change audited: {details[:3]}"
        sc = status_change[0]["status"]
        assert "from" in sc and "to" in sc
        rate_change = [d for d in details if "per_delivery_rate" in d]
        assert rate_change, "pricing change not audited"
        assert rate_change[0]["per_delivery_rate"]["to"] == 33.0
        # cleanup
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                     json={"per_delivery_rate": None}, timeout=60)

    def test_nonexistent_facility(self, admin_token):
        r = requests.put(f"{API}/facilities/does-not-exist", headers=h(admin_token),
                         json={"status": "approved"}, timeout=60)
        assert r.status_code == 404, r.text[:300]


# ---- RBAC: owner edits ----
class TestOwnerRBAC:
    def test_owner_edit_ignores_admin_fields(self, admin_token, facility_token, fac1):
        fid = fac1["id"]
        # admin sets known terms first
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "status": "approved", "per_delivery_rate": 12.0, "commission_rate_override": 0.25
        }, timeout=60)
        r = requests.put(f"{API}/facilities/{fid}", headers=h(facility_token), json={
            "contact_name": "TEST Owner Contact",
            "status": "suspended",
            "per_delivery_rate": 999.0,
            "commission_rate_override": 0.99,
        }, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["contact_name"] == "TEST Owner Contact"
        assert d["status"] == "approved", "owner escalated status!"
        assert d["per_delivery_rate"] == 12.0, "owner changed pricing!"
        assert d["commission_rate_override"] == 0.25, "owner changed commission!"
        # restore
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "contact_name": fac1.get("contact_name") or "Facility Contact",
            "per_delivery_rate": None, "commission_rate_override": None,
        }, timeout=60)

    def test_driver_cannot_edit_facility(self, driver_token, fac1):
        r = requests.put(f"{API}/facilities/{fac1['id']}", headers=h(driver_token),
                         json={"name": "TEST hack"}, timeout=60)
        assert r.status_code == 403, r.text[:300]


# ---- Suspend blocks booking ----
class TestSuspendBlocksBooking:
    def test_suspend_then_book_blocked_then_reapprove(self, admin_token, facility_token, fac1, created_job_ids):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"status": "suspended"}, timeout=60).status_code == 200
        payload = {
            "pickup_address": PICKUP, "dropoff_address": DROPOFF,
            "item_category": "lab_sample", "handling_flags": [],
            "item_count": 1, "recipient_name": "TEST Recipient", "recipient_phone": "4165550000", "requested_pickup_time": "2026-07-20T10:00:00Z",
        }
        r = requests.post(f"{API}/facility/requests", headers=h(facility_token), json=payload, timeout=90)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:300]}"
        assert "suspend" in r.json().get("detail", "").lower()

        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"status": "approved"}, timeout=60).status_code == 200
        r = requests.post(f"{API}/facility/requests", headers=h(facility_token), json=payload, timeout=90)
        assert r.status_code == 201, r.text[:300]
        created_job_ids.append(r.json()["id"])

    def test_inflight_job_can_advance_while_suspended(self, admin_token, facility_token, driver_token, fac1, created_job_ids):
        fid = fac1["id"]
        payload = {
            "pickup_address": PICKUP, "dropoff_address": DROPOFF,
            "item_category": "lab_sample", "handling_flags": [],
            "item_count": 1, "recipient_name": "TEST Inflight", "recipient_phone": "4165550001", "requested_pickup_time": "2026-07-20T10:00:00Z",
        }
        r = requests.post(f"{API}/facility/requests", headers=h(facility_token), json=payload, timeout=90)
        assert r.status_code == 201, r.text[:300]
        job_id = r.json()["id"]
        created_job_ids.append(job_id)
        # driver accepts
        acc = requests.post(f"{API}/jobs/{job_id}/accept", headers=h(driver_token), timeout=60)
        assert acc.status_code in (200, 201), acc.text[:300]
        # suspend facility
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={"status": "suspended"}, timeout=60)
        # in-flight job can still advance
        up = requests.put(f"{API}/jobs/{job_id}", headers=h(driver_token), json={"status": "picked_up"}, timeout=60)
        assert up.status_code == 200, f"in-flight job blocked: {up.status_code} {up.text[:300]}"
        assert up.json()["status"] == "picked_up"
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={"status": "approved"}, timeout=60)


# ---- Pricing ----
class TestPerDeliveryRatePricing:
    def _book(self, facility_token, flags, name):
        payload = {
            "pickup_address": PICKUP, "dropoff_address": DROPOFF,
            "item_category": "lab_sample", "handling_flags": flags,
            "item_count": 1, "recipient_name": name, "recipient_phone": "4165550002", "requested_pickup_time": "2026-07-20T10:00:00Z",
        }
        return requests.post(f"{API}/facility/requests", headers=h(facility_token), json=payload, timeout=90)

    def test_flat_rate_and_surcharges(self, admin_token, facility_token, fac1, created_job_ids):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"status": "approved", "per_delivery_rate": 40}, timeout=60).status_code == 200

        r = self._book(facility_token, [], "TEST Flat")
        assert r.status_code == 201, r.text[:300]
        created_job_ids.append(r.json()["id"])
        assert r.json()["payout_amount"] == 40.00, r.json()["payout_amount"]
        assert r.json()["offered_price"] == 40.00

        r = self._book(facility_token, ["urgent"], "TEST Urgent")
        assert r.status_code == 201, r.text[:300]
        created_job_ids.append(r.json()["id"])
        assert r.json()["payout_amount"] == 60.00, r.json()["payout_amount"]

        r = self._book(facility_token, ["cold_chain"], "TEST Cold")
        assert r.status_code == 201, r.text[:300]
        created_job_ids.append(r.json()["id"])
        assert r.json()["payout_amount"] == 55.00, r.json()["payout_amount"]

    def test_clearing_rate_reverts_to_distance(self, admin_token, facility_token, fac1, created_job_ids):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token),
                            json={"per_delivery_rate": None}, timeout=60).status_code == 200
        r = self._book(facility_token, [], "TEST Distance")
        assert r.status_code == 201, r.text[:300]
        j = r.json()
        created_job_ids.append(j["id"])
        expected = round(max(25.0, 1.5 * float(j["distance_km"])), 2)
        assert j["payout_amount"] == expected, f"{j['payout_amount']} != {expected} for {j['distance_km']}km"
        assert j["payout_amount"] != 40.00


# ---- Commission override ----
class TestCommissionOverride:
    def _complete_cycle(self, facility_token, driver_token, admin_token, created_job_ids, name):
        payload = {
            "pickup_address": PICKUP, "dropoff_address": DROPOFF,
            "item_category": "lab_sample", "handling_flags": [],
            "item_count": 1, "recipient_name": name, "recipient_phone": "4165550003", "requested_pickup_time": "2026-07-20T10:00:00Z",
        }
        r = requests.post(f"{API}/facility/requests", headers=h(facility_token), json=payload, timeout=90)
        assert r.status_code == 201, r.text[:300]
        job = r.json()
        created_job_ids.append(job["id"])
        acc = requests.post(f"{API}/jobs/{job['id']}/accept", headers=h(driver_token), timeout=60)
        assert acc.status_code in (200, 201), acc.text[:300]
        pu = requests.post(f"{API}/jobs/{job['id']}/custody-events", headers=h(driver_token), json={
            "event_type": "pickup_confirmed",
            "checklist": {"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True},
        }, timeout=60)
        assert pu.status_code == 201, f"pickup: {pu.text[:300]}"
        dl = requests.post(f"{API}/jobs/{job['id']}/custody-events", headers=h(driver_token), json={
            "event_type": "delivered",
            "recipient_name": "TEST Recipient",
            "evidence_url": "https://example.com/signature.png",
        }, timeout=60)
        assert dl.status_code == 201, f"delivered: {dl.text[:300]}"
        time.sleep(1)
        return job

    def test_override_applied_to_ledger(self, admin_token, facility_token, driver_token, fac1, created_job_ids):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "status": "approved", "per_delivery_rate": 50, "commission_rate_override": 0.10
        }, timeout=60).status_code == 200
        job = self._complete_cycle(facility_token, driver_token, admin_token, created_job_ids, "TEST Commission10")
        gross = float(job["payout_amount"])
        assert gross == 50.00

        r = requests.get(f"{API}/admin/ledger", headers=h(admin_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        entries = r.json().get("entries") or r.json().get("ledger") or []
        mine = [e for e in entries if e.get("job_id") == job["id"] and e.get("type") == "commission"]
        assert mine, f"no commission ledger entry for job {job['id']}; keys={list(r.json().keys())}"
        e = mine[0]
        assert e["amount"] == round(gross * 0.10, 2), e
        assert "10% platform commission" in e.get("description", ""), e.get("description")

    def test_global_rate_when_no_override(self, admin_token, facility_token, driver_token, fac1, created_job_ids):
        fid = fac1["id"]
        assert requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "commission_rate_override": None
        }, timeout=60).status_code == 200
        job = self._complete_cycle(facility_token, driver_token, admin_token, created_job_ids, "TEST Commission20")
        gross = float(job["payout_amount"])
        r = requests.get(f"{API}/admin/ledger", headers=h(admin_token), timeout=60)
        entries = r.json().get("entries") or r.json().get("ledger") or []
        mine = [e for e in entries if e.get("job_id") == job["id"] and e.get("type") == "commission"]
        assert mine, f"no commission entry for job {job['id']}"
        assert mine[0]["amount"] == round(gross * 0.20, 2), mine[0]
        # restore terms
        requests.put(f"{API}/facilities/{fid}", headers=h(admin_token), json={
            "per_delivery_rate": None, "commission_rate_override": None, "status": "approved"
        }, timeout=60)


# ---- Regression ----
class TestRegression:
    def test_dispatch_board(self, dispatcher_token):
        r = requests.get(f"{API}/dispatch/board", headers=h(dispatcher_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "jobs" in r.json() and "approved_drivers" in r.json()

    def test_facility_deliveries(self, facility_token):
        r = requests.get(f"{API}/facility/deliveries", headers=h(facility_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json()["deliveries"], list)

    def test_admin_driver_verifications(self, admin_token):
        r = requests.get(f"{API}/admin/driver-verifications", headers=h(admin_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
