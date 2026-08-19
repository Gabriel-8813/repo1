"""Tests for Permits CRUD, cancel_job order fix, and regression checks (iteration 4)."""
import os
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "gabrielosmanhamza@yahoo.com"
ADMIN_PASS = "Admin@123"
DRIVER_EMAIL = "driver1@test.com"
DRIVER_PASS = "Driver@123"


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)


def _ensure(email, password, full_name, phone):
    r = _login(email, password)
    if r.status_code == 200:
        return r.json()
    rr = requests.post(f"{API}/auth/register",
                       json={ "privacy_policy_accepted": True, "email": email, "password": password, "full_name": full_name, "phone": phone},
                       timeout=15)
    if rr.status_code == 200:
        return rr.json()
    r2 = _login(email, password)
    assert r2.status_code == 200, f"cannot auth {email}: {rr.text}"
    return r2.json()


@pytest.fixture(scope="session")
def admin_auth():
    data = _ensure(ADMIN_EMAIL, ADMIN_PASS, "Gabriel Admin", "+14165551234")
    assert data["user"]["role"] == "admin"
    return data


@pytest.fixture(scope="session")
def driver_auth():
    return _ensure(DRIVER_EMAIL, DRIVER_PASS, "Driver One", "+14165550001")


@pytest.fixture(scope="session")
def admin_headers(admin_auth):
    return {"Authorization": f"Bearer {admin_auth['access_token']}"}


@pytest.fixture(scope="session")
def driver_headers(driver_auth):
    return {"Authorization": f"Bearer {driver_auth['access_token']}"}


# ---- Permits public ----
class TestPermitsPublic:
    def test_get_permits_returns_seeded_six(self):
        r = requests.get(f"{API}/permits")
        assert r.status_code == 200
        permits = r.json()["permits"]
        assert len(permits) >= 6
        ids = [p["id"] for p in permits]
        # Seeded permits must be present
        for expected in ["cvor", "tdg", "driver_license", "vulnerable_sector", "vehicle_insurance", "first_aid"]:
            assert expected in ids, f"missing seeded permit {expected}"
        # Ordered by 'order' ascending
        orders = [p.get("order", 0) for p in permits]
        assert orders == sorted(orders)


# ---- Admin Permits CRUD ----
class TestAdminPermitsCRUD:
    def test_admin_list_permits(self, admin_headers):
        r = requests.get(f"{API}/admin/permits", headers=admin_headers)
        assert r.status_code == 200
        assert len(r.json()["permits"]) >= 6

    def test_driver_forbidden_admin_permits(self, driver_headers):
        r = requests.get(f"{API}/admin/permits", headers=driver_headers)
        assert r.status_code == 403

    def test_full_crud_flow(self, admin_headers):
        new_id = "test_permit_crud"
        # Cleanup in case leftover
        requests.delete(f"{API}/admin/permits/{new_id}", headers=admin_headers)

        # CREATE
        payload = {
            "id": new_id,
            "name": "TEST Permit",
            "description": "Temporary test permit",
            "issuing_authority": "Test Auth",
            "url": "https://example.com",
            "required": True,
        }
        r = requests.post(f"{API}/admin/permits", headers=admin_headers, json=payload)
        assert r.status_code == 200, r.text
        created = r.json()["permit"]
        assert created["id"] == new_id
        assert created["name"] == "TEST Permit"

        # DUPLICATE -> 400
        rdup = requests.post(f"{API}/admin/permits", headers=admin_headers, json=payload)
        assert rdup.status_code == 400

        # Verify it appears on public /permits
        pub = requests.get(f"{API}/permits").json()["permits"]
        assert any(p["id"] == new_id for p in pub)

        # UPDATE
        ru = requests.put(f"{API}/admin/permits/{new_id}", headers=admin_headers,
                          json={"name": "TEST Permit Updated", "required": False})
        assert ru.status_code == 200
        assert ru.json()["permit"]["name"] == "TEST Permit Updated"
        assert ru.json()["permit"]["required"] is False

        # UPDATE unknown -> 404
        r404 = requests.put(f"{API}/admin/permits/nonexistent_xyz", headers=admin_headers,
                            json={"name": "x"})
        assert r404.status_code == 404

        # DELETE
        rd = requests.delete(f"{API}/admin/permits/{new_id}", headers=admin_headers)
        assert rd.status_code == 200

        # DELETE again -> 404
        rd2 = requests.delete(f"{API}/admin/permits/{new_id}", headers=admin_headers)
        assert rd2.status_code == 404

        # No longer on public permits
        pub2 = requests.get(f"{API}/permits").json()["permits"]
        assert not any(p["id"] == new_id for p in pub2)


# ---- cancel_job status-before-driver fix ----
class TestCancelJobOrderFix:
    def test_cancel_open_job_returns_400(self, driver_headers, admin_headers):
        # Create an 'open' job (unassigned) - post as admin (driver can also post)
        payload = {
            "title": "TEST_cancel_open",
            "pickup_address": "1 Queen St",
            "delivery_address": "2 King St",
            "pickup_city": "Toronto",
            "delivery_city": "Mississauga",
            "goods_type": "lab_samples",
            "temperature_controlled": False,
            "urgency": "standard",
            "estimated_distance_km": 10.0,
            "offered_price": 50.0,
        }
        r = requests.post(f"{API}/jobs", headers=admin_headers, json=payload)
        assert r.status_code == 200
        job_id = r.json()["id"]

        try:
            # Driver attempts to cancel an OPEN job (not accepted) -> should be 400 now
            rc = requests.post(f"{API}/jobs/{job_id}/cancel", headers=driver_headers)
            assert rc.status_code == 400, f"expected 400 got {rc.status_code}: {rc.text}"
            detail = rc.json().get("detail", "").lower()
            assert any(w in detail for w in ("active", "open", "cancel")), detail
        finally:
            # Cleanup: admin delete the job
            requests.delete(f"{API}/admin/jobs/{job_id}", headers=admin_headers)


# ---- Regression: admin stats, balance, ledger ----
class TestRegression:
    def test_admin_stats_commission_shape(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        for k in ["total_users", "commission_owed", "commission_paid",
                  "cancellation_fees_owed", "cancellation_fees_paid",
                  "total_revenue", "total_outstanding"]:
            assert k in data, f"missing {k}"

    def test_driver_balance(self, driver_headers):
        r = requests.get(f"{API}/driver/balance", headers=driver_headers)
        assert r.status_code == 200
        d = r.json()
        assert "owed" in d and "paid" in d and "entries" in d

    def test_admin_ledger(self, admin_headers):
        r = requests.get(f"{API}/admin/ledger", headers=admin_headers)
        assert r.status_code == 200
        assert "entries" in r.json()

    def test_driver_no_admin_access(self, driver_headers):
        for path in ["/admin/stats", "/admin/users", "/admin/jobs", "/admin/fees", "/admin/ledger", "/admin/permits"]:
            r = requests.get(f"{API}{path}", headers=driver_headers)
            assert r.status_code == 403, f"{path} should forbid driver"

    def test_admin_login_auto_promote(self):
        r = _login(ADMIN_EMAIL, ADMIN_PASS)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"
