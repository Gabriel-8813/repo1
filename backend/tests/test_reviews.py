"""End-to-end tests for Driver Ratings & Reviews (iteration_8).

Covers:
- Public GET /api/reviews/info/{job_id}   (404 / 400 / 200)
- Public POST /api/reviews/{job_id}       (422 / 400 / 404 / 200 / duplicate-400)
- Public GET /api/drivers/{driver_id}/reviews (sort desc; hidden excluded)
- Auth   GET /api/driver/reviews (driver's own)
- Admin  GET /api/admin/reviews (all, inc. hidden)
- Admin  POST /api/admin/reviews/{id}/hide (soft-hide; summary recompute)
- Admin  DELETE /api/admin/reviews/{id} (404 unknown; RBAC driver->403)
- Regression: admin/stats, driver/balance, permits
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


# ---------- fixtures ----------
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


def _make_completed_job(api_client, admin_token, driver_token, label="REV"):
    title = f"TEST_{label}_{uuid.uuid4().hex[:8]}"
    payload = {
        "title": title, "pickup_address": "123 QA St", "delivery_address": "456 QA Ave",
        "pickup_city": "Toronto", "delivery_city": "Ottawa", "goods_type": "blood_samples",
        "estimated_distance_km": 100.0, "offered_price": 200.0, "urgency": "normal",
    }
    r = api_client.post(f"{API}/jobs", json=payload,
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    r = api_client.post(f"{API}/jobs/{jid}/accept",
                        headers={"Authorization": f"Bearer {driver_token}"})
    assert r.status_code == 200
    r = api_client.post(f"{API}/jobs/{jid}/complete",
                        headers={"Authorization": f"Bearer {driver_token}"})
    assert r.status_code == 200
    return jid


@pytest.fixture(scope="module")
def created_jobs(api_client, admin_token, driver_token):
    """Creates 3 completed jobs for the driver; cleans them at end."""
    jids = [_make_completed_job(api_client, admin_token, driver_token) for _ in range(3)]
    yield jids

    async def _cleanup():
        cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
        for jid in jids:
            await db.jobs.delete_one({"id": jid})
            await db.reviews.delete_many({"job_id": jid})
            await db.earnings.delete_many({"job_id": jid})
            await db.ledger.delete_many({"job_id": jid})
        cli.close()
    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.fixture(scope="module")
def open_job(api_client, admin_token):
    """An open (not completed) job for negative-path tests."""
    r = api_client.post(
        f"{API}/jobs",
        json={
            "title": f"TEST_OPENR_{uuid.uuid4().hex[:6]}",
            "pickup_address": "a", "delivery_address": "b",
            "pickup_city": "Toronto", "delivery_city": "Ottawa",
            "goods_type": "documents", "estimated_distance_km": 10.0,
            "offered_price": 50.0, "urgency": "normal",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    jid = r.json()["id"]
    yield jid

    async def _d():
        cli = AsyncIOMotorClient(MONGO_URL); db = cli[DB_NAME]
        await db.jobs.delete_one({"id": jid}); cli.close()
    asyncio.get_event_loop().run_until_complete(_d())


# ---------- /api/reviews/info ----------
class TestReviewInfo:
    def test_info_unknown_job_404(self, api_client):
        r = api_client.get(f"{API}/reviews/info/no-such-id-xyz")
        assert r.status_code == 404

    def test_info_non_completed_400(self, api_client, open_job):
        r = api_client.get(f"{API}/reviews/info/{open_job}")
        assert r.status_code == 400

    def test_info_completed_returns_shape(self, api_client, created_jobs):
        r = api_client.get(f"{API}/reviews/info/{created_jobs[0]}")
        assert r.status_code == 200
        d = r.json()
        assert "trip" in d and "driver" in d
        assert "already_reviewed" in d and d["already_reviewed"] is False
        assert "driver_rating" in d
        assert set(d["driver_rating"].keys()) >= {"avg", "count"}
        assert d["trip"]["id"] == created_jobs[0]
        assert isinstance(d["driver"]["first_name"], str)


# ---------- /api/reviews POST ----------
class TestSubmitReview:
    def test_rating_below_1_returns_422(self, api_client, created_jobs):
        r = api_client.post(f"{API}/reviews/{created_jobs[0]}", json={"rating": 0})
        assert r.status_code == 422

    def test_rating_above_5_returns_422(self, api_client, created_jobs):
        r = api_client.post(f"{API}/reviews/{created_jobs[0]}", json={"rating": 6})
        assert r.status_code == 422

    def test_unknown_job_404(self, api_client):
        r = api_client.post(f"{API}/reviews/no-such-xyz", json={"rating": 5})
        assert r.status_code == 404

    def test_non_completed_job_400(self, api_client, open_job):
        r = api_client.post(f"{API}/reviews/{open_job}", json={"rating": 5})
        assert r.status_code == 400

    def test_submit_success_and_shape(self, api_client, created_jobs, driver_id):
        jid = created_jobs[0]
        r = api_client.post(f"{API}/reviews/{jid}", json={
            "rating": 5, "comment": "Excellent driver!", "reviewer_name": "TEST_Customer_A"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert "review" in d and "driver_rating" in d
        rev = d["review"]
        assert rev["rating"] == 5
        assert rev["comment"] == "Excellent driver!"
        assert rev["reviewer_name"] == "TEST_Customer_A"
        assert rev["job_id"] == jid
        assert rev["driver_id"] == driver_id
        assert rev["hidden"] is False
        assert "id" in rev and "created_at" in rev
        assert d["driver_rating"]["count"] >= 1
        assert d["driver_rating"]["avg"] > 0

        # Verify persistence: info endpoint now says already_reviewed=true
        r2 = api_client.get(f"{API}/reviews/info/{jid}")
        assert r2.status_code == 200
        assert r2.json()["already_reviewed"] is True

    def test_duplicate_review_returns_400(self, api_client, created_jobs):
        # 2nd submission on same job should 400
        jid = created_jobs[0]
        r = api_client.post(f"{API}/reviews/{jid}", json={"rating": 3})
        assert r.status_code == 400
        assert "already been reviewed" in r.text.lower()


# ---------- Public driver reviews list + summary ----------
class TestPublicDriverReviews:
    def test_list_reviews_and_summary(self, api_client, created_jobs, driver_id):
        # Submit review on 2nd job (3 stars)
        jid2 = created_jobs[1]
        r = api_client.post(f"{API}/reviews/{jid2}", json={"rating": 3, "comment": "ok"})
        assert r.status_code == 200

        r = api_client.get(f"{API}/drivers/{driver_id}/reviews")
        assert r.status_code == 200
        d = r.json()
        assert "reviews" in d and "summary" in d
        reviews = d["reviews"]
        # Only reviews for this driver — all test-created ones so far
        our = [rev for rev in reviews if rev["job_id"] in created_jobs]
        assert len(our) >= 2
        # Sorted desc by created_at: newer first
        times = [rev["created_at"] for rev in our]
        assert times == sorted(times, reverse=True)
        # Summary: avg of visible reviews, e.g. (5+3)/2 = 4.0
        avg = d["summary"]["avg"]
        cnt = d["summary"]["count"]
        assert cnt >= 2
        assert 1 <= avg <= 5


# ---------- Auth: driver's own reviews ----------
class TestDriverReviewsAuth:
    def test_driver_reviews_requires_auth(self, api_client):
        r = api_client.get(f"{API}/driver/reviews")
        assert r.status_code in (401, 403)

    def test_driver_reviews_returns_own(self, api_client, driver_token, driver_id):
        r = api_client.get(f"{API}/driver/reviews",
                           headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 200
        d = r.json()
        assert "reviews" in d and "summary" in d
        for rev in d["reviews"]:
            assert rev["driver_id"] == driver_id


# ---------- Admin list / hide / delete + RBAC ----------
class TestAdminReviews:
    def test_admin_reviews_requires_admin(self, api_client, driver_token):
        r = api_client.get(f"{API}/admin/reviews",
                           headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 403

    def test_admin_reviews_lists_all(self, api_client, admin_token, created_jobs):
        r = api_client.get(f"{API}/admin/reviews",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        all_ids = {rev["job_id"] for rev in r.json()["reviews"]}
        # Our 2 submitted reviews are present
        assert created_jobs[0] in all_ids
        assert created_jobs[1] in all_ids

    def test_hide_review_excludes_from_public_and_recomputes_summary(
        self, api_client, admin_token, created_jobs, driver_id
    ):
        # Submit a 3rd review (1 star) on job 3
        jid3 = created_jobs[2]
        r = api_client.post(f"{API}/reviews/{jid3}", json={"rating": 1, "comment": "TEST_hide_target"})
        assert r.status_code == 200
        review_id = r.json()["review"]["id"]

        # Public summary before hide
        before = api_client.get(f"{API}/drivers/{driver_id}/reviews").json()
        before_count = before["summary"]["count"]
        before_avg = before["summary"]["avg"]
        assert any(rev["id"] == review_id for rev in before["reviews"])

        # Admin hides
        h = api_client.post(f"{API}/admin/reviews/{review_id}/hide",
                            headers={"Authorization": f"Bearer {admin_token}"})
        assert h.status_code == 200
        assert h.json()["status"] == "hidden"

        # Public no longer includes it, and summary recomputes
        after = api_client.get(f"{API}/drivers/{driver_id}/reviews").json()
        assert all(rev["id"] != review_id for rev in after["reviews"])
        assert after["summary"]["count"] == before_count - 1
        # avg changes because lowest rating removed -> avg should rise (or stay if boundary)
        assert after["summary"]["avg"] >= before_avg

        # Admin list still includes hidden
        admin_all = api_client.get(f"{API}/admin/reviews",
                                   headers={"Authorization": f"Bearer {admin_token}"}).json()
        hidden = [rev for rev in admin_all["reviews"] if rev["id"] == review_id]
        assert len(hidden) == 1 and hidden[0]["hidden"] is True

    def test_hide_unknown_returns_404(self, api_client, admin_token):
        r = api_client.post(f"{API}/admin/reviews/does-not-exist/hide",
                            headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 404

    def test_delete_rbac_driver_forbidden(self, api_client, driver_token):
        r = api_client.delete(f"{API}/admin/reviews/anything",
                              headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 403

    def test_delete_unknown_404(self, api_client, admin_token):
        r = api_client.delete(f"{API}/admin/reviews/does-not-exist",
                              headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 404

    def test_delete_removes_review(self, api_client, admin_token, created_jobs):
        # Find existing review from job[1]
        admin_all = api_client.get(f"{API}/admin/reviews",
                                   headers={"Authorization": f"Bearer {admin_token}"}).json()
        target = next(rev for rev in admin_all["reviews"] if rev["job_id"] == created_jobs[1])
        rid = target["id"]
        d = api_client.delete(f"{API}/admin/reviews/{rid}",
                              headers={"Authorization": f"Bearer {admin_token}"})
        assert d.status_code == 200
        assert d.json()["status"] == "deleted"

        # Verify gone
        admin_all2 = api_client.get(f"{API}/admin/reviews",
                                    headers={"Authorization": f"Bearer {admin_token}"}).json()
        assert all(rev["id"] != rid for rev in admin_all2["reviews"])


# ---------- Regression ----------
class TestRegression:
    def test_admin_stats_200(self, api_client, admin_token):
        r = api_client.get(f"{API}/admin/stats",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200

    def test_driver_balance_200(self, api_client, driver_token):
        r = api_client.get(f"{API}/driver/balance",
                           headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 200

    def test_permits_list_200(self, api_client):
        r = api_client.get(f"{API}/permits")
        assert r.status_code == 200

    def test_driver_tips_200(self, api_client, driver_token):
        r = api_client.get(f"{API}/driver/tips",
                           headers={"Authorization": f"Bearer {driver_token}"})
        assert r.status_code == 200
