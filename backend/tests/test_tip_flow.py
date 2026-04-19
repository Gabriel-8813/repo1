"""End-to-end tests for the Tip Your Driver flow (iteration_6).

Covers:
- Public GET /api/tips/info/{job_id}  (404 / 400 / 200 with presets)
- Public POST /api/tips/checkout/{job_id}  (validation + Stripe session create)
- Public GET /api/tips/status/{session_id}  (idempotent paid-settlement via mongo mock)
- Driver earnings crediting (type='tip')
- Authenticated GET /api/driver/tips
- Commission/balance settlement regression
"""
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

_FE = dotenv_values("/app/frontend/.env")
_BE = dotenv_values("/app/backend/.env")
BASE_URL = (_FE.get("REACT_APP_BACKEND_URL") or os.environ.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = _BE.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = (_BE.get("DB_NAME") or os.environ.get("DB_NAME")).strip('"')

ADMIN = {"email": "gabrielosmanhamza@yahoo.com", "password": "Admin@123"}
DRIVER = {"email": "driver1@test.com", "password": "Driver@123"}


# ---------- shared helpers / fixtures ----------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(client, creds):
    r = client.post(f"{API}/auth/login", json=creds)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token(api_client):
    return _login(api_client, ADMIN)


@pytest.fixture(scope="module")
def driver_token(api_client):
    return _login(api_client, DRIVER)


@pytest.fixture(scope="module")
def driver_id(api_client, driver_token):
    r = api_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {driver_token}"})
    assert r.status_code == 200
    return r.json()["id"]


@pytest.fixture(scope="module")
def completed_job(api_client, admin_token, driver_token):
    """Create → accept → complete a TEST_* job so that /tips/* can work on it."""
    title = f"TEST_TIP_{uuid.uuid4().hex[:8]}"
    payload = {
        "title": title,
        "pickup_address": "123 QA St",
        "delivery_address": "456 QA Ave",
        "pickup_city": "Toronto",
        "delivery_city": "Ottawa",
        "goods_type": "blood_samples",
        "estimated_distance_km": 100.0,
        "offered_price": 200.0,
        "urgency": "normal",
    }
    r = api_client.post(
        f"{API}/jobs", json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    job = r.json()
    job_id = job["id"]

    r = api_client.post(
        f"{API}/jobs/{job_id}/accept",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert r.status_code == 200, r.text

    r = api_client.post(
        f"{API}/jobs/{job_id}/complete",
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert r.status_code == 200, r.text

    yield job_id

    # Teardown — clean up created job and any tip artifacts
    async def _cleanup():
        cli = AsyncIOMotorClient(MONGO_URL)
        db = cli[DB_NAME]
        await db.jobs.delete_one({"id": job_id})
        await db.earnings.delete_many({"job_id": job_id})
        await db.payment_transactions.delete_many({"job_id": job_id})
        await db.ledger.delete_many({"job_id": job_id})
        cli.close()
    asyncio.get_event_loop().run_until_complete(_cleanup())


# ---------- /api/tips/info ----------
class TestTipInfo:
    def test_info_unknown_job_returns_404(self, api_client):
        r = api_client.get(f"{API}/tips/info/no-such-id-xyz")
        assert r.status_code == 404

    def test_info_non_completed_returns_400(self, api_client, admin_token):
        # Create an open (not completed) job
        r = api_client.post(
            f"{API}/jobs",
            json={
                "title": f"TEST_OPEN_{uuid.uuid4().hex[:6]}",
                "pickup_address": "a", "delivery_address": "b",
                "pickup_city": "Toronto", "delivery_city": "Ottawa",
                "goods_type": "documents",
                "estimated_distance_km": 10.0,
                "offered_price": 50.0, "urgency": "normal",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        jid = r.json()["id"]
        try:
            r2 = api_client.get(f"{API}/tips/info/{jid}")
            assert r2.status_code == 400
        finally:
            # cleanup
            async def _d():
                cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
                await db.jobs.delete_one({"id": jid}); cli.close()
            asyncio.get_event_loop().run_until_complete(_d())

    def test_info_completed_returns_presets_and_driver(self, api_client, completed_job):
        r = api_client.get(f"{API}/tips/info/{completed_job}")
        assert r.status_code == 200, r.text
        data = r.json()
        # shape
        assert "trip" in data and "driver" in data and "presets" in data
        assert data["currency"] == "CAD"
        # trip details
        assert data["trip"]["id"] == completed_job
        assert data["trip"]["offered_price"] == 200.0
        # driver first_name
        assert "first_name" in data["driver"]
        assert isinstance(data["driver"]["first_name"], str) and len(data["driver"]["first_name"]) > 0
        # presets 15/20/25
        assert len(data["presets"]) == 3
        labels = [p["label"] for p in data["presets"]]
        assert labels == ["15%", "20%", "25%"]
        amounts = [p["amount"] for p in data["presets"]]
        assert amounts == [30.0, 40.0, 50.0]


# ---------- /api/tips/checkout validation ----------
class TestTipCheckoutValidation:
    def test_checkout_zero_amount_400(self, api_client, completed_job):
        r = api_client.post(
            f"{API}/tips/checkout/{completed_job}",
            json={"amount": 0, "origin_url": BASE_URL},
        )
        assert r.status_code == 400

    def test_checkout_negative_amount_400(self, api_client, completed_job):
        r = api_client.post(
            f"{API}/tips/checkout/{completed_job}",
            json={"amount": -5, "origin_url": BASE_URL},
        )
        assert r.status_code == 400

    def test_checkout_above_max_400(self, api_client, completed_job):
        r = api_client.post(
            f"{API}/tips/checkout/{completed_job}",
            json={"amount": 10001, "origin_url": BASE_URL},
        )
        assert r.status_code == 400

    def test_checkout_unknown_job_404(self, api_client):
        r = api_client.post(
            f"{API}/tips/checkout/does-not-exist",
            json={"amount": 5, "origin_url": BASE_URL},
        )
        assert r.status_code == 404

    def test_checkout_non_completed_job_400(self, api_client, admin_token):
        r = api_client.post(
            f"{API}/jobs",
            json={
                "title": f"TEST_OPEN_{uuid.uuid4().hex[:6]}",
                "pickup_address": "a", "delivery_address": "b",
                "pickup_city": "Toronto", "delivery_city": "Ottawa",
                "goods_type": "documents",
                "estimated_distance_km": 10.0,
                "offered_price": 50.0, "urgency": "normal",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        jid = r.json()["id"]
        try:
            r2 = api_client.post(
                f"{API}/tips/checkout/{jid}",
                json={"amount": 10, "origin_url": BASE_URL},
            )
            assert r2.status_code == 400
        finally:
            async def _d():
                cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
                await db.jobs.delete_one({"id": jid}); cli.close()
            asyncio.get_event_loop().run_until_complete(_d())


# ---------- Full tip happy-path + idempotency ----------
class TestTipCheckoutAndSettle:
    def test_checkout_creates_session_and_payment_transaction(self, api_client, completed_job, driver_id):
        r = api_client.post(
            f"{API}/tips/checkout/{completed_job}",
            json={"amount": 15.5, "origin_url": BASE_URL, "tipper_name": "QA Tipper"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "checkout_url" in d and "session_id" in d
        assert d["checkout_url"].startswith("http")
        assert "stripe.com" in d["checkout_url"]
        assert d["amount"] == 15.5

        # Verify payment_transactions record
        async def _check():
            cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
            tx = await db.payment_transactions.find_one({"session_id": d["session_id"]}, {"_id": 0})
            cli.close()
            return tx
        tx = asyncio.get_event_loop().run_until_complete(_check())
        assert tx is not None
        assert tx["payment_type"] == "tip"
        assert tx["job_id"] == completed_job
        assert tx["driver_id"] == driver_id
        assert tx["amount"] == 15.5
        assert tx["payment_status"] == "initiated"

        # store for next tests
        pytest.tip_session_id = d["session_id"]

    def test_paid_tip_credits_earnings_and_is_idempotent(self, api_client, completed_job, driver_id):
        """Simulate paid webhook by flipping payment_status then calling internal settle logic.
        /tips/status hits Stripe which won't return paid for unpaid session, so we call
        _settle_ledger_for_session directly via mongo-flip + import."""
        session_id = getattr(pytest, "tip_session_id", None)
        assert session_id, "tip_session_id missing from earlier test"

        async def _flip_and_settle():
            cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid", "status": "complete"}},
            )
            cli.close()
            # Call the settle helper directly
            import sys
            sys.path.insert(0, "/app/backend")
            from server import _settle_ledger_for_session
            await _settle_ledger_for_session(session_id)
            await _settle_ledger_for_session(session_id)  # call twice → idempotent

        asyncio.get_event_loop().run_until_complete(_flip_and_settle())

        # Verify exactly ONE earnings row
        async def _check():
            cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
            rows = await db.earnings.find(
                {"payment_session_id": session_id}, {"_id": 0}
            ).to_list(10)
            cli.close()
            return rows
        rows = asyncio.get_event_loop().run_until_complete(_check())
        assert len(rows) == 1, f"expected 1 earnings row, got {len(rows)}: {rows}"
        row = rows[0]
        assert row["type"] == "tip"
        assert row["driver_id"] == driver_id
        assert row["amount"] == 15.5
        assert row["job_id"] == completed_job

    def test_driver_tips_endpoint_reflects_total(self, api_client, driver_token, completed_job):
        r = api_client.get(
            f"{API}/driver/tips",
            headers={"Authorization": f"Bearer {driver_token}"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["currency"] == "CAD"
        assert "tips" in d and "total" in d and "count" in d
        # Must contain our tip
        our_tips = [t for t in d["tips"] if t.get("job_id") == completed_job]
        assert len(our_tips) == 1
        assert our_tips[0]["amount"] == 15.5
        assert d["total"] >= 15.5

    def test_driver_tips_requires_auth(self, api_client):
        r = api_client.get(f"{API}/driver/tips")
        assert r.status_code in (401, 403)


# ---------- Regression: balance/commission settlement still works ----------
class TestCommissionRegression:
    def test_balance_settle_still_marks_ledger_paid(self, api_client, driver_id):
        """Create a fake ledger 'owed' + matching paid payment_transactions, then settle."""
        ledger_id = str(uuid.uuid4())
        session_id = f"cs_test_regression_{uuid.uuid4().hex[:10]}"

        async def _setup_and_settle():
            cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
            await db.ledger.insert_one({
                "id": ledger_id, "driver_id": driver_id,
                "type": "commission", "amount": 10.0, "status": "owed",
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            await db.payment_transactions.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": driver_id,
                "session_id": session_id,
                "payment_type": "balance",
                "ledger_ids": [ledger_id],
                "amount": 10.0, "currency": "cad",
                "status": "complete", "payment_status": "paid",
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            import sys; sys.path.insert(0, "/app/backend")
            from server import _settle_ledger_for_session
            await _settle_ledger_for_session(session_id)
            row = await db.ledger.find_one({"id": ledger_id}, {"_id": 0})
            # cleanup
            await db.ledger.delete_one({"id": ledger_id})
            await db.payment_transactions.delete_one({"session_id": session_id})
            cli.close()
            return row

        row = asyncio.get_event_loop().run_until_complete(_setup_and_settle())
        assert row["status"] == "paid"
        assert row.get("payment_session_id") == session_id
