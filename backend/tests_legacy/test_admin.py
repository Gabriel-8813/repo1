"""Admin RBAC & admin CRUD tests for MediTrans Ontario."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    from pathlib import Path
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
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return r


def _register_if_missing(email, password, full_name, phone):
    r = _login(email, password)
    if r.status_code == 200:
        return r.json()
    rr = requests.post(f"{API}/auth/register", json={
        "email": email, "password": password, "full_name": full_name, "phone": phone
    }, timeout=15)
    if rr.status_code == 200:
        return rr.json()
    # If register failed because already exists but creds wrong, still try login
    r2 = _login(email, password)
    assert r2.status_code == 200, f"cannot login or register {email}: {rr.status_code} {rr.text}"
    return r2.json()


@pytest.fixture(scope="session")
def admin_auth():
    data = _register_if_missing(ADMIN_EMAIL, ADMIN_PASS, "Gabriel Admin", "+14165551234")
    assert data["user"]["role"] == "admin", f"Admin not auto-promoted: {data['user']}"
    return data


@pytest.fixture(scope="session")
def driver_auth():
    data = _register_if_missing(DRIVER_EMAIL, DRIVER_PASS, "Driver One", "+14165550001")
    return data


@pytest.fixture(scope="session")
def admin_headers(admin_auth):
    return {"Authorization": f"Bearer {admin_auth['access_token']}"}


@pytest.fixture(scope="session")
def driver_headers(driver_auth):
    return {"Authorization": f"Bearer {driver_auth['access_token']}"}


# ---- Auto-promotion ----
class TestAdminAutoPromotion:
    def test_admin_role_in_db(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_driver_role(self, driver_headers):
        r = requests.get(f"{API}/auth/me", headers=driver_headers)
        assert r.status_code == 200
        assert r.json()["role"] == "driver"


# ---- RBAC ----
class TestAdminRBAC:
    @pytest.mark.parametrize("method,path", [
        ("GET", "/admin/stats"),
        ("GET", "/admin/users"),
        ("GET", "/admin/jobs"),
        ("GET", "/admin/plans"),
        ("GET", "/admin/fees"),
        ("GET", "/admin/transactions"),
    ])
    def test_driver_forbidden(self, driver_headers, method, path):
        r = requests.request(method, f"{API}{path}", headers=driver_headers)
        assert r.status_code == 403, f"{path} should return 403 for driver, got {r.status_code}"

    def test_no_auth_unauthorized(self):
        r = requests.get(f"{API}/admin/stats")
        assert r.status_code == 401


# ---- Stats ----
class TestAdminStats:
    def test_stats_structure(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        for k in ["total_users", "active_subscriptions", "total_jobs", "total_revenue"]:
            assert k in data, f"missing {k}"
        assert isinstance(data["total_users"], int)
        assert data["total_users"] >= 2


# ---- Users ----
class TestAdminUsers:
    def test_list_users_no_sensitive_fields(self, admin_headers):
        r = requests.get(f"{API}/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()["users"]
        assert len(users) >= 2
        for u in users:
            assert "password_hash" not in u
            assert "_id" not in u

    def test_update_user_role_and_persist(self, admin_headers, driver_auth):
        uid = driver_auth["user"]["id"]
        # Promote driver -> admin
        r = requests.put(f"{API}/admin/users/{uid}", headers=admin_headers,
                         json={"role": "admin", "subscription_plan": "pro", "subscription_status": "active"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"
        assert r.json()["user"]["subscription_plan"] == "pro"
        # Revert back
        r2 = requests.put(f"{API}/admin/users/{uid}", headers=admin_headers,
                          json={"role": "driver", "subscription_plan": None, "subscription_status": None})
        # Note: None values are filtered out in backend model; clear directly via another update if needed
        assert r2.status_code == 200
        # Force revert role back to driver
        r3 = requests.put(f"{API}/admin/users/{uid}", headers=admin_headers, json={"role": "driver"})
        assert r3.json()["user"]["role"] == "driver"

    def test_update_user_invalid_role(self, admin_headers, driver_auth):
        uid = driver_auth["user"]["id"]
        r = requests.put(f"{API}/admin/users/{uid}", headers=admin_headers, json={"role": "superuser"})
        assert r.status_code == 400

    def test_delete_self_forbidden(self, admin_headers, admin_auth):
        r = requests.delete(f"{API}/admin/users/{admin_auth['user']['id']}", headers=admin_headers)
        assert r.status_code == 400

    def test_delete_then_recreate(self, admin_headers):
        # Create throwaway user
        email = "TEST_delete_me@example.com"
        try:
            requests.post(f"{API}/auth/register", json={
                "email": email, "password": "Test@123", "full_name": "ToDelete", "phone": "+10000000000"
            })
        except Exception:
            pass
        login = _login(email, "Test@123")
        assert login.status_code == 200
        uid = login.json()["user"]["id"]
        r = requests.delete(f"{API}/admin/users/{uid}", headers=admin_headers)
        assert r.status_code == 200
        # Verify gone
        r2 = _login(email, "Test@123")
        assert r2.status_code == 401


# ---- Jobs ----
class TestAdminJobs:
    @pytest.fixture
    def sample_job(self, driver_headers):
        payload = {
            "title": "TEST_admin_job",
            "pickup_address": "1 Queen St",
            "delivery_address": "2 King St",
            "pickup_city": "Toronto",
            "delivery_city": "Mississauga",
            "goods_type": "lab_samples",
            "temperature_controlled": False,
            "urgency": "standard",
            "estimated_distance_km": 15.0,
            "offered_price": 60.0
        }
        r = requests.post(f"{API}/jobs", headers=driver_headers, json=payload)
        assert r.status_code == 200
        return r.json()

    def test_list_jobs(self, admin_headers, sample_job):
        r = requests.get(f"{API}/admin/jobs", headers=admin_headers)
        assert r.status_code == 200
        assert any(j["id"] == sample_job["id"] for j in r.json()["jobs"])

    def test_update_job_invalid_status(self, admin_headers, sample_job):
        r = requests.put(f"{API}/admin/jobs/{sample_job['id']}", headers=admin_headers,
                         json={"status": "garbage"})
        assert r.status_code == 400

    def test_update_job_and_delete(self, admin_headers, sample_job):
        r = requests.put(f"{API}/admin/jobs/{sample_job['id']}", headers=admin_headers,
                         json={"title": "TEST_updated", "offered_price": 88.8, "urgency": "urgent"})
        assert r.status_code == 200
        job = r.json()["job"]
        assert job["title"] == "TEST_updated"
        assert job["offered_price"] == 88.8
        # Delete
        rd = requests.delete(f"{API}/admin/jobs/{sample_job['id']}", headers=admin_headers)
        assert rd.status_code == 200
        rd2 = requests.delete(f"{API}/admin/jobs/{sample_job['id']}", headers=admin_headers)
        assert rd2.status_code == 404


# ---- Plans ----
class TestAdminPlans:
    def test_get_plans(self, admin_headers):
        r = requests.get(f"{API}/admin/plans", headers=admin_headers)
        assert r.status_code == 200
        plans = r.json()["plans"]
        for key in ["basic", "pro", "premium"]:
            assert key in plans

    def test_update_plan_and_public_reflects(self, admin_headers):
        # Save original
        orig = requests.get(f"{API}/admin/plans", headers=admin_headers).json()["plans"]["pro"]
        try:
            r = requests.put(f"{API}/admin/plans/pro", headers=admin_headers,
                             json={"price": 123.45, "features": ["TEST feat"]})
            assert r.status_code == 200
            assert r.json()["plans"]["pro"]["price"] == 123.45
            pub = requests.get(f"{API}/subscriptions/plans").json()["plans"]
            assert pub["pro"]["price"] == 123.45
            assert "TEST feat" in pub["pro"]["features"]
        finally:
            # Restore defaults
            requests.put(f"{API}/admin/plans/pro", headers=admin_headers,
                         json={"name": orig["name"], "price": orig["price"], "features": orig["features"]})

    def test_update_plan_not_found(self, admin_headers):
        r = requests.put(f"{API}/admin/plans/nope", headers=admin_headers, json={"price": 1})
        assert r.status_code == 404


# ---- Fees ----
class TestAdminFees:
    def test_get_and_update_fees(self, admin_headers):
        orig = requests.get(f"{API}/admin/fees", headers=admin_headers).json()["agreement"]
        try:
            r = requests.put(f"{API}/admin/fees", headers=admin_headers, json={"base_rate_per_km": 2.22})
            assert r.status_code == 200
            assert r.json()["agreement"]["base_rate_per_km"] == 2.22
            pub = requests.get(f"{API}/fees/agreement").json()["agreement"]
            assert pub["base_rate_per_km"] == 2.22
        finally:
            requests.put(f"{API}/admin/fees", headers=admin_headers, json={
                "base_rate_per_km": orig.get("base_rate_per_km", 1.50),
                "minimum_fee": orig.get("minimum_fee", 25.0),
                "urgent_multiplier": orig.get("urgent_multiplier", 1.5),
                "emergency_multiplier": orig.get("emergency_multiplier", 2.0),
                "temperature_controlled_fee": orig.get("temperature_controlled_fee", 15.0),
                "platform_commission": orig.get("platform_commission", 0.15),
            })


# ---- Transactions ----
class TestAdminTransactions:
    def test_list_transactions(self, admin_headers):
        r = requests.get(f"{API}/admin/transactions", headers=admin_headers)
        assert r.status_code == 200
        assert "transactions" in r.json()
        assert isinstance(r.json()["transactions"], list)
