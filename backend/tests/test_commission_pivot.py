"""
Tests for the commission-based revenue pivot (MediTrans Ontario).
- Verifies subscription endpoints are removed
- Accept job without subscription
- Complete job -> 20% commission ledger entry
- Cancel within grace -> free, job reopens
- Cancel after grace (backdated accepted_at) -> $15 cancellation fee ledger entry
- Admin stats/ledger/fees endpoints
- RBAC on /api/admin/*
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://medtrans-admin.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "gabrielosmanhamza@yahoo.com"
ADMIN_PASS = "Admin@123"
DRIVER_EMAIL = "driver1@test.com"
DRIVER_PASS = "Driver@123"

# Mongo direct access for simulation (backdating accepted_at)
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017').strip('"').strip("'")
DB_NAME = os.environ.get('DB_NAME', 'test_database').strip('"').strip("'")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return r


def _register(email, password, full_name="Test User", phone="+1-647-555-0000"):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": password, "full_name": full_name, "phone": phone
    }, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASS)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    data = r.json()
    assert data["user"]["role"] == "admin", f"Admin auto-promote failed: role={data['user']['role']}"
    return data["access_token"]


@pytest.fixture(scope="module")
def driver_token():
    r = _login(DRIVER_EMAIL, DRIVER_PASS)
    if r.status_code != 200:
        # try register
        r = _register(DRIVER_EMAIL, DRIVER_PASS, "Test Driver", "+1-647-555-0101")
        if r.status_code not in (200, 201):
            pytest.skip(f"Driver login/register failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def driver_id(driver_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {driver_token}"}, timeout=15)
    return r.json()["id"]


@pytest.fixture(scope="module")
def second_driver_token():
    email = f"driver2_{uuid.uuid4().hex[:6]}@test.com"
    r = _register(email, "Driver@123", "Test Driver 2", "+1-647-555-0202")
    if r.status_code not in (200, 201):
        pytest.skip(f"Second driver register failed: {r.text}")
    return r.json()["access_token"]


# ---------- Subscription endpoints removed ----------
class TestSubscriptionRemoved:
    def test_subscriptions_plans_gone(self):
        r = requests.get(f"{API}/subscriptions/plans", timeout=10)
        assert r.status_code == 404

    def test_admin_plans_gone(self, admin_token):
        r = requests.get(f"{API}/admin/plans", headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 404

    def test_payments_checkout_with_plan_gone(self, driver_token):
        # Legacy endpoint /api/payments/checkout with plan_id should no longer exist
        r = requests.post(f"{API}/payments/checkout",
                          headers={"Authorization": f"Bearer {driver_token}"},
                          json={"plan_id": "basic", "origin_url": BASE_URL}, timeout=10)
        assert r.status_code == 404, f"Expected 404 got {r.status_code}: {r.text[:200]}"


# ---------- Fee Agreement ----------
class TestFeeAgreement:
    def test_public_fee_agreement(self):
        r = requests.get(f"{API}/fees/agreement", timeout=10)
        assert r.status_code == 200
        a = r.json()["agreement"]
        assert a.get("commission_rate") == 0.20
        assert a.get("cancellation_fee") == 15.00
        assert a.get("cancellation_grace_minutes") == 5
        assert "platform_commission" not in a

    def test_admin_update_fees_roundtrip(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        # Change and restore
        r = requests.put(f"{API}/admin/fees", headers=h,
                         json={"commission_rate": 0.25, "cancellation_fee": 20.00, "cancellation_grace_minutes": 10},
                         timeout=10)
        assert r.status_code == 200
        a = r.json()["agreement"]
        assert a["commission_rate"] == 0.25
        assert a["cancellation_fee"] == 20.00
        assert a["cancellation_grace_minutes"] == 10
        # restore
        r2 = requests.put(f"{API}/admin/fees", headers=h,
                          json={"commission_rate": 0.20, "cancellation_fee": 15.00, "cancellation_grace_minutes": 5,
                                "base_rate_per_km": 1.5, "minimum_fee": 25.0,
                                "urgent_multiplier": 1.5, "emergency_multiplier": 2.0,
                                "temperature_controlled_fee": 15.0},
                          timeout=10)
        assert r2.status_code == 200


# ---------- Commission flow ----------
class TestCommissionFlow:
    def test_driver_accept_complete_creates_commission(self, driver_token, driver_id):
        h = {"Authorization": f"Bearer {driver_token}"}
        # create job (drivers can post jobs — used in app)
        job_payload = {
            "title": "TEST Commission Run",
            "pickup_address": "1 Test St", "delivery_address": "2 Test Ave",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "medical_sample", "temperature_controlled": False,
            "urgency": "standard", "estimated_distance_km": 100, "offered_price": 200.00
        }
        r = requests.post(f"{API}/jobs", headers=h, json=job_payload, timeout=10)
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]

        # accept WITHOUT subscription — should succeed
        r = requests.post(f"{API}/jobs/{job_id}/accept", headers=h, timeout=10)
        assert r.status_code == 200, f"Accept without sub should work, got {r.status_code}: {r.text}"

        # complete
        r = requests.post(f"{API}/jobs/{job_id}/complete", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["gross_earnings"] == 200.0
        assert data["commission_charged"] == 40.0   # 20%
        assert data["net_earnings"] == 160.0

        # Verify ledger entry
        r = requests.get(f"{API}/driver/balance", headers=h, timeout=10)
        assert r.status_code == 200
        bal = r.json()
        matching = [e for e in bal["entries"] if e.get("job_id") == job_id and e.get("type") == "commission"]
        assert matching, f"No commission ledger entry for job {job_id}"
        assert matching[0]["amount"] == 40.0
        assert matching[0]["status"] == "owed"

    def test_cancel_within_grace_no_charge(self, driver_token):
        h = {"Authorization": f"Bearer {driver_token}"}
        r = requests.post(f"{API}/jobs", headers=h, json={
            "title": "TEST Grace Cancel", "pickup_address": "a", "delivery_address": "b",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "sample", "temperature_controlled": False,
            "urgency": "standard", "estimated_distance_km": 50, "offered_price": 100.00
        }, timeout=10)
        job_id = r.json()["id"]
        requests.post(f"{API}/jobs/{job_id}/accept", headers=h, timeout=10)

        r = requests.post(f"{API}/jobs/{job_id}/cancel", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["charged"] is False
        assert data["cancellation_fee"] == 0
        # job should be reopened
        job = requests.get(f"{API}/jobs/available", headers=h, timeout=10).json()["jobs"]
        assert any(j["id"] == job_id and j["status"] == "open" and j["accepted_by"] is None for j in job)

    def test_cancel_after_grace_charges_fee(self, driver_token, driver_id):
        h = {"Authorization": f"Bearer {driver_token}"}
        r = requests.post(f"{API}/jobs", headers=h, json={
            "title": "TEST Late Cancel", "pickup_address": "a", "delivery_address": "b",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "sample", "temperature_controlled": False,
            "urgency": "standard", "estimated_distance_km": 50, "offered_price": 100.00
        }, timeout=10)
        job_id = r.json()["id"]
        requests.post(f"{API}/jobs/{job_id}/accept", headers=h, timeout=10)

        # Backdate accepted_at by 10 min via Mongo
        async def backdate():
            c = AsyncIOMotorClient(MONGO_URL)
            d = c[DB_NAME]
            past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            res = await d.jobs.update_one({"id": job_id}, {"$set": {"accepted_at": past}})
            c.close()
            return res.modified_count
        modified = asyncio.get_event_loop().run_until_complete(backdate())
        assert modified == 1, "Failed to backdate accepted_at in mongo"

        r = requests.post(f"{API}/jobs/{job_id}/cancel", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["charged"] is True
        assert data["cancellation_fee"] == 15.00
        assert data["ledger_entry"]["type"] == "cancellation_fee"
        assert data["ledger_entry"]["status"] == "owed"

    def test_cancel_403_if_not_assigned(self, driver_token, second_driver_token):
        # driver 1 creates & accepts
        h1 = {"Authorization": f"Bearer {driver_token}"}
        r = requests.post(f"{API}/jobs", headers=h1, json={
            "title": "TEST RBAC cancel", "pickup_address": "a", "delivery_address": "b",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "sample", "temperature_controlled": False,
            "urgency": "standard", "estimated_distance_km": 50, "offered_price": 100.00
        }, timeout=10)
        job_id = r.json()["id"]
        requests.post(f"{API}/jobs/{job_id}/accept", headers=h1, timeout=10)
        # driver 2 attempts cancel
        h2 = {"Authorization": f"Bearer {second_driver_token}"}
        r = requests.post(f"{API}/jobs/{job_id}/cancel", headers=h2, timeout=10)
        assert r.status_code == 403
        # cleanup: driver1 cancels (within grace)
        requests.post(f"{API}/jobs/{job_id}/cancel", headers=h1, timeout=10)

    def test_cancel_400_if_not_in_progress(self, driver_token):
        h = {"Authorization": f"Bearer {driver_token}"}
        r = requests.post(f"{API}/jobs", headers=h, json={
            "title": "TEST open cancel", "pickup_address": "a", "delivery_address": "b",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "sample", "temperature_controlled": False,
            "urgency": "standard", "estimated_distance_km": 50, "offered_price": 100.00
        }, timeout=10)
        job_id = r.json()["id"]
        r = requests.post(f"{API}/jobs/{job_id}/cancel", headers=h, timeout=10)
        assert r.status_code == 400


# ---------- Balance checkout ----------
class TestBalanceCheckout:
    def test_checkout_400_when_no_balance(self):
        """Create a brand-new driver (zero ledger) and ensure 400."""
        email = f"fresh_{uuid.uuid4().hex[:6]}@test.com"
        r = _register(email, "Driver@123", "Fresh Driver", "+1-647-555-0303")
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        r = requests.post(f"{API}/payments/balance/checkout", headers=h,
                          json={"origin_url": BASE_URL}, timeout=15)
        assert r.status_code == 400

    def test_checkout_with_balance_returns_url(self, driver_token):
        h = {"Authorization": f"Bearer {driver_token}"}
        bal = requests.get(f"{API}/driver/balance", headers=h, timeout=10).json()
        if bal["owed"] <= 0:
            pytest.skip("No outstanding balance for driver1")
        r = requests.post(f"{API}/payments/balance/checkout", headers=h,
                          json={"origin_url": BASE_URL}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://")
        assert d.get("session_id")


# ---------- Admin ----------
class TestAdminEndpoints:
    def test_admin_stats_new_shape(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/stats", headers=h, timeout=10)
        assert r.status_code == 200
        s = r.json()
        for k in ["commission_owed", "commission_paid", "cancellation_fees_owed",
                  "cancellation_fees_paid", "total_revenue", "total_outstanding"]:
            assert k in s, f"Missing {k} in admin stats"
        assert "active_subscriptions" not in s

    def test_admin_ledger_lists_entries(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/ledger", headers=h, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json().get("entries"), list)

    def test_admin_users_no_subscription_fields(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/admin/users", headers=h, timeout=10)
        assert r.status_code == 200
        users = r.json()["users"]
        for u in users:
            assert "subscription_plan" not in u
            assert "subscription_status" not in u
            assert "subscription_expires" not in u

    def test_rbac_driver_blocked_on_admin(self, driver_token):
        h = {"Authorization": f"Bearer {driver_token}"}
        for path in ["/admin/stats", "/admin/users", "/admin/jobs", "/admin/fees", "/admin/ledger", "/admin/transactions"]:
            r = requests.get(f"{API}{path}", headers=h, timeout=10)
            assert r.status_code == 403, f"{path} should be 403 for driver, got {r.status_code}"


# ---------- Cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup(request):
    yield
    # Cleanup: delete TEST_ jobs/ledger/earnings, keep driver1 test data minimal.
    async def do_cleanup():
        c = AsyncIOMotorClient(MONGO_URL)
        d = c[DB_NAME]
        # find TEST jobs
        test_jobs = await d.jobs.find({"title": {"$regex": "^TEST"}}, {"id": 1, "_id": 0}).to_list(1000)
        ids = [j["id"] for j in test_jobs]
        if ids:
            await d.jobs.delete_many({"id": {"$in": ids}})
            await d.ledger.delete_many({"job_id": {"$in": ids}})
            await d.earnings.delete_many({"job_id": {"$in": ids}})
        # Reset fees to defaults (defensive)
        await d.settings.update_one(
            {"key": "fee_agreement"},
            {"$set": {"value": {
                "base_rate_per_km": 1.5, "minimum_fee": 25.0,
                "urgent_multiplier": 1.5, "emergency_multiplier": 2.0,
                "temperature_controlled_fee": 15.0,
                "commission_rate": 0.20, "cancellation_fee": 15.0,
                "cancellation_grace_minutes": 5, "currency": "CAD"
            }}}, upsert=True
        )
        c.close()
    asyncio.get_event_loop().run_until_complete(do_cleanup())
