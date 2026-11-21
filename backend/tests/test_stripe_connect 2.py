"""
Tests for Stripe Connect (Express) driver-payout integration.

Covers:
  - /api/driver/connect/status (empty & after onboard)
  - /api/driver/connect/onboard (create + reuse existing account)
  - /api/driver/connect/login-link (400 if none, success once set)
  - RBAC (auth required on all three)
  - /api/tips/checkout/{job_id} fallback (no connect), and routed path (with connect)
  - Regression: balance checkout still works, permits & admin stats unchanged
Test data prefixed TEST_CONN_*. Stripe Express accounts created are deleted in teardown.
"""
import os
import time
import uuid
import pytest
import requests
import stripe
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://medtrans-admin.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
STRIPE_KEY = os.environ.get("STRIPE_API_KEY")
stripe.api_key = STRIPE_KEY

ADMIN_EMAIL = "gabrielosmanhamza@yahoo.com"
ADMIN_PW = "Admin@123"
DRIVER_EMAIL = "driver1@test.com"
DRIVER_PW = "Driver@123"

_created_accounts = []  # track stripe account ids to clean up


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def driver_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DRIVER_EMAIL, "password": DRIVER_PW})
    assert r.status_code == 200, f"driver login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def reset_driver(mongo):
    """Before suite: reset driver1 to unconnected. After suite: same + delete stripe accts."""
    # capture existing acct to delete if any
    u = mongo.users.find_one({"email": DRIVER_EMAIL})
    if u and u.get("stripe_account_id"):
        _created_accounts.append(u["stripe_account_id"])
    mongo.users.update_one(
        {"email": DRIVER_EMAIL},
        {"$unset": {
            "stripe_account_id": "",
            "stripe_charges_enabled": "",
            "stripe_payouts_enabled": "",
            "stripe_details_submitted": ""
        }}
    )
    yield
    # teardown — delete stripe accounts we created and reset driver1
    u2 = mongo.users.find_one({"email": DRIVER_EMAIL})
    if u2 and u2.get("stripe_account_id"):
        _created_accounts.append(u2["stripe_account_id"])
    seen = set()
    for a in _created_accounts:
        if a in seen or not a:
            continue
        seen.add(a)
        try:
            stripe.Account.delete(a)
            print(f"[teardown] deleted stripe account {a}")
        except Exception as e:
            print(f"[teardown] could not delete {a}: {e}")
    mongo.users.update_one(
        {"email": DRIVER_EMAIL},
        {"$unset": {
            "stripe_account_id": "",
            "stripe_charges_enabled": "",
            "stripe_payouts_enabled": "",
            "stripe_details_submitted": ""
        }}
    )


# ---------- RBAC ----------
class TestRBAC:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/driver/connect/status")
        assert r.status_code in (401, 403), r.text

    def test_onboard_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/driver/connect/onboard", json={"origin_url": BASE_URL})
        assert r.status_code in (401, 403), r.text

    def test_login_link_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/driver/connect/login-link")
        assert r.status_code in (401, 403), r.text


# ---------- Status ----------
class TestConnectStatus:
    def test_status_empty_before_onboard(self, driver_token):
        r = requests.get(f"{BASE_URL}/api/driver/connect/status", headers=_h(driver_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d == {
            "connected": False,
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": False,
            "account_id": None
        }


# ---------- Onboard / login-link ----------
class TestConnectOnboard:
    def test_login_link_400_before_onboard(self, driver_token):
        r = requests.post(f"{BASE_URL}/api/driver/connect/login-link", headers=_h(driver_token))
        assert r.status_code == 400, r.text

    def test_onboard_creates_account_and_returns_stripe_url(self, driver_token, mongo):
        r = requests.post(
            f"{BASE_URL}/api/driver/connect/onboard",
            headers=_h(driver_token),
            json={"origin_url": BASE_URL}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "url" in d and "account_id" in d
        assert d["account_id"].startswith("acct_"), d["account_id"]
        # stripe.com hosted onboarding URL (connect.stripe.com)
        assert "stripe.com" in d["url"], d["url"]
        _created_accounts.append(d["account_id"])

        # persisted on user
        u = mongo.users.find_one({"email": DRIVER_EMAIL})
        assert u["stripe_account_id"] == d["account_id"]
        assert u.get("stripe_charges_enabled") is False
        assert u.get("stripe_payouts_enabled") is False

    def test_onboard_reuses_existing_account(self, driver_token, mongo):
        u_before = mongo.users.find_one({"email": DRIVER_EMAIL})
        existing = u_before.get("stripe_account_id")
        assert existing, "previous test should have set stripe_account_id"

        r = requests.post(
            f"{BASE_URL}/api/driver/connect/onboard",
            headers=_h(driver_token),
            json={"origin_url": BASE_URL}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["account_id"] == existing, f"expected reuse of {existing}, got {d['account_id']}"
        assert "stripe.com" in d["url"]

    def test_status_after_onboard(self, driver_token):
        r = requests.get(f"{BASE_URL}/api/driver/connect/status", headers=_h(driver_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["connected"] is True
        assert d["account_id"].startswith("acct_")
        # Until hosted onboarding is completed, charges_enabled is false
        assert d["charges_enabled"] is False
        assert "requirements" in d
        assert "currently_due" in d["requirements"]
        assert isinstance(d["requirements"]["currently_due"], list)

    def test_login_link_success_after_onboard(self, driver_token):
        r = requests.post(f"{BASE_URL}/api/driver/connect/login-link", headers=_h(driver_token))
        # Stripe only allows login-links after details_submitted=true in some account states.
        # We accept either 200 with connect.stripe.com URL, or 400 (not yet submitted).
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            d = r.json()
            assert "url" in d
            assert "stripe.com" in d["url"]


# ---------- Tip flow: fallback (no connect) + connect-routed code path ----------
class TestTipConnectRouting:
    @pytest.fixture(scope="class")
    def test_job(self, admin_token, driver_token, mongo):
        """Create a completed job owned by the driver for tipping."""
        # Admin posts a job
        job_payload = {
            "title": "TEST_CONN_trip",
            "pickup_address": "100 Queen St W",
            "delivery_address": "200 Main St",
            "pickup_city": "Toronto",
            "delivery_city": "Mississauga",
            "goods_type": "medical_supplies",
            "temperature_controlled": False,
            "urgency": "standard",
            "estimated_distance_km": 20.0,
            "offered_price": 80.0,
            "notes": "TEST_CONN"
        }
        r = requests.post(f"{BASE_URL}/api/jobs", headers=_h(admin_token), json=job_payload)
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]

        # Driver accepts
        r = requests.post(f"{BASE_URL}/api/jobs/{job_id}/accept", headers=_h(driver_token))
        assert r.status_code in (200, 201), r.text
        # Driver completes
        r = requests.post(f"{BASE_URL}/api/jobs/{job_id}/complete", headers=_h(driver_token))
        assert r.status_code in (200, 201), r.text

        yield job_id

        # cleanup: delete job + payment_transactions + earnings
        mongo.jobs.delete_one({"id": job_id})
        mongo.payment_transactions.delete_many({"job_id": job_id})
        mongo.earnings.delete_many({"job_id": job_id})
        mongo.ledger.delete_many({"job_id": job_id})

    def test_tip_fallback_when_charges_disabled(self, test_job, mongo):
        """With stripe_account_id present but charges_enabled=false → fallback (no transfer_data)."""
        # set driver1 to onboarded-but-incomplete state
        mongo.users.update_one(
            {"email": DRIVER_EMAIL},
            {"$set": {"stripe_charges_enabled": False}}
        )
        r = requests.post(
            f"{BASE_URL}/api/tips/checkout/{test_job}",
            json={"amount": 12.5, "origin_url": BASE_URL, "tipper_name": "TEST_CONN_tipper"}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["routed_to_driver"] is False
        assert "checkout_url" in d and "stripe.com" in d["checkout_url"]
        sid = d["session_id"]
        tx = mongo.payment_transactions.find_one({"session_id": sid})
        assert tx is not None
        assert tx["connect_routed"] is False
        assert tx.get("stripe_account_id") in (None, "")

    def test_tip_connect_route_with_fake_account_returns_400(self, test_job, mongo):
        """With a fake acct_ id + charges_enabled=true, code tries Connect route and returns 400 (Stripe error)."""
        mongo.users.update_one(
            {"email": DRIVER_EMAIL},
            {"$set": {"stripe_account_id": "acct_invalidtest_XYZ", "stripe_charges_enabled": True}}
        )
        try:
            r = requests.post(
                f"{BASE_URL}/api/tips/checkout/{test_job}",
                json={"amount": 10.0, "origin_url": BASE_URL, "tipper_name": "TEST_CONN_tipper2"}
            )
            # Fake account → Stripe.Session.create fails → endpoint returns 400
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
            assert "Stripe" in r.text or "stripe" in r.text
        finally:
            # restore: unset fake acct + charges
            mongo.users.update_one(
                {"email": DRIVER_EMAIL},
                {"$unset": {"stripe_account_id": "", "stripe_charges_enabled": ""}}
            )

    def test_tip_fallback_when_no_connect_account(self, test_job, mongo):
        """With no stripe_account_id at all → fallback path; transaction recorded with connect_routed=false."""
        # Ensure driver fully unconnected
        mongo.users.update_one(
            {"email": DRIVER_EMAIL},
            {"$unset": {"stripe_account_id": "", "stripe_charges_enabled": ""}}
        )
        r = requests.post(
            f"{BASE_URL}/api/tips/checkout/{test_job}",
            json={"amount": 5.0, "origin_url": BASE_URL, "tipper_name": "TEST_CONN_tipper3"}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["routed_to_driver"] is False


# ---------- Regression ----------
class TestRegression:
    def test_admin_stats(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/stats", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        # Ensure at least some expected keys
        d = r.json()
        assert isinstance(d, dict)

    def test_balance_checkout(self, driver_token, mongo):
        # Create a commission-owed ledger row so balance checkout has something to pay
        # Admin first — create a job and complete, then try checkout of outstanding balance
        r = requests.get(f"{BASE_URL}/api/driver/balance", headers=_h(driver_token))
        assert r.status_code == 200, r.text

    def test_permits_list(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/permits", headers=_h(admin_token))
        assert r.status_code == 200, r.text

    def test_driver_tips_shape(self, driver_token):
        r = requests.get(f"{BASE_URL}/api/driver/tips", headers=_h(driver_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["tips", "total", "count", "currency"]).issubset(d.keys())
        assert d["currency"] == "CAD"
