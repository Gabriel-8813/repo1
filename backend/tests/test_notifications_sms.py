"""Tests for real-time notifications, dev-mode SMS outbox, CASL compliance,
public delivery confirmation link, and stale-job sweep notifications."""
import io
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

CREDS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
    "driver": ("driver1@test.com", "Driver@123"),
    "facility": ("facility1@test.com", "Facility@123"),
}
RECIPIENT_PHONE = "+14165559999"


def _login(role):
    email, password = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Login failed for {role}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    if not tok:
        pytest.fail(f"No access_token for {role}: {r.text[:300]}")
    return tok


@pytest.fixture(scope="module")
def tokens():
    return {role: _login(role) for role in CREDS}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def created_job_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(tokens, created_job_ids):
    yield
    admin = tokens["admin"]
    for jid in created_job_ids:
        requests.delete(f"{API}/admin/jobs/{jid}", headers=H(admin), timeout=30)
    requests.post(f"{API}/admin/sms-optouts", headers=H(admin),
                  json={"phone": RECIPIENT_PHONE, "action": "remove"}, timeout=30)


def book_job(tokens, created_job_ids, consent=True, title_suffix=""):
    payload = {
        "recipient_name": f"TEST_QA Recipient{title_suffix}",
        "dropoff_address": "100 Queen St W, Toronto, ON",
        "recipient_phone": RECIPIENT_PHONE,
        "item_count": 2,
        "item_category": "prescription",
        "handling_flags": [],
        "special_instructions": "TEST_QA notifications suite",
        "requested_pickup_time": "2026-07-20T15:00:00Z",
        "recipient_sms_consent": consent,
    }
    r = requests.post(f"{API}/facility/requests", headers=H(tokens["facility"]), json=payload, timeout=60)
    assert r.status_code in (200, 201), f"booking failed: {r.status_code} {r.text[:400]}"
    job = r.json()
    assert job["recipient_sms_consent"] is consent
    created_job_ids.append(job["id"])
    return job


def outbox_for(tokens, job_id):
    r = requests.get(f"{API}/admin/sms-outbox?limit=500", headers=H(tokens["admin"]), timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    return [m for m in data["messages"] if m.get("job_id") == job_id], data


def accept_as_driver(tokens, job_id):
    return requests.post(f"{API}/jobs/{job_id}/accept", headers=H(tokens["driver"]), timeout=30)


def upload_signature(tokens, job_id):
    png = (b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    r = requests.post(f"{API}/jobs/{job_id}/delivery-evidence", headers=H(tokens["driver"]),
                      files={"file": ("sig.png", io.BytesIO(png), "image/png")},
                      data={"kind": "signature"}, timeout=60)
    assert r.status_code == 201, f"evidence upload failed: {r.status_code} {r.text[:300]}"
    return r.json()["evidence_url"]


# ---- SMS flow E2E (consented job) ----
class TestSmsFlowE2E:
    def test_full_sms_flow(self, tokens, created_job_ids):
        job = book_job(tokens, created_job_ids, consent=True, title_suffix=" WITH consent")
        jid = job["id"]

        # driver accepts -> 'assigned' SMS
        r = accept_as_driver(tokens, jid)
        assert r.status_code == 200, f"accept failed: {r.status_code} {r.text[:300]}"
        time.sleep(1)
        msgs, meta = outbox_for(tokens, jid)
        assert meta["twilio_configured"] is False
        assigned = [m for m in msgs if m["kind"] == "assigned"]
        assert len(assigned) == 1, f"expected 1 assigned SMS, got {msgs}"
        assert assigned[0]["status"] == "dev_outbox"
        assert assigned[0]["body"].endswith("Reply STOP to opt out.")
        assert assigned[0]["to_phone"] == RECIPIENT_PHONE

        # arriving-soon invalid before pickup
        r = requests.post(f"{API}/jobs/{jid}/arriving-soon", headers=H(tokens["driver"]), timeout=30)
        assert r.status_code == 400, r.text[:200]

        # pickup confirmed -> out_for_delivery
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                          json={"event_type": "pickup_confirmed",
                                "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
        assert r.status_code == 201, f"pickup failed: {r.status_code} {r.text[:300]}"
        time.sleep(1)
        msgs, _ = outbox_for(tokens, jid)
        ofd = [m for m in msgs if m["kind"] == "out_for_delivery"]
        assert len(ofd) == 1 and ofd[0]["status"] == "dev_outbox"
        assert ofd[0]["body"].endswith("Reply STOP to opt out.")

        # facility cannot trigger arriving-soon
        r = requests.post(f"{API}/jobs/{jid}/arriving-soon", headers=H(tokens["facility"]), timeout=30)
        assert r.status_code == 403, r.text[:200]

        # driver arriving-soon -> arriving SMS; second call skipped
        r = requests.post(f"{API}/jobs/{jid}/arriving-soon", headers=H(tokens["driver"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "dev_outbox"
        r2 = requests.post(f"{API}/jobs/{jid}/arriving-soon", headers=H(tokens["driver"]), timeout=30)
        assert r2.status_code == 200 and r2.json()["status"] == "skipped", r2.text[:200]
        msgs, _ = outbox_for(tokens, jid)
        assert len([m for m in msgs if m["kind"] == "arriving"]) == 1

        # delivered -> delivered SMS with /confirm/{token}
        evidence_url = upload_signature(tokens, jid)
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=60,
                          json={"event_type": "delivered", "evidence_url": evidence_url,
                                "recipient_name": "TEST_QA Recipient"})
        assert r.status_code == 201, f"delivered failed: {r.status_code} {r.text[:300]}"
        time.sleep(1.5)
        msgs, _ = outbox_for(tokens, jid)
        delivered = [m for m in msgs if m["kind"] == "delivered"]
        assert len(delivered) == 1, f"expected 1 delivered SMS, got {msgs}"
        assert "/confirm/" in delivered[0]["body"], delivered[0]["body"]
        assert delivered[0]["body"].endswith("Reply STOP to opt out.")

        # all four kinds exactly once
        kinds = sorted(m["kind"] for m in msgs)
        assert kinds == ["arriving", "assigned", "delivered", "out_for_delivery"], kinds

        # stash token for confirmation tests
        token = delivered[0]["body"].split("/confirm/")[1].split()[0].rstrip(".")
        TestConfirmLink.token = token
        TestConfirmLink.job_id = jid


# ---- CASL: no consent means no SMS ----
class TestCaslNoConsent:
    def test_no_sms_without_consent(self, tokens, created_job_ids):
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" NO consent")
        jid = job["id"]
        r = accept_as_driver(tokens, jid)
        assert r.status_code == 200, r.text[:300]
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                          json={"event_type": "pickup_confirmed",
                                "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
        assert r.status_code == 201, r.text[:300]
        r = requests.post(f"{API}/jobs/{jid}/arriving-soon", headers=H(tokens["driver"]), timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "skipped"
        evidence_url = upload_signature(tokens, jid)
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=60,
                          json={"event_type": "delivered", "evidence_url": evidence_url,
                                "recipient_name": "TEST_QA NoConsent"})
        assert r.status_code == 201, r.text[:300]
        time.sleep(1)
        msgs, _ = outbox_for(tokens, jid)
        assert msgs == [], f"SMS sent without consent: {msgs}"


# ---- Opt-out (STOP webhook + admin management) ----
class TestOptOut:
    def test_stop_webhook_and_blocked_send(self, tokens, created_job_ids):
        r = requests.post(f"{API}/sms/twilio-webhook",
                          data={"From": RECIPIENT_PHONE, "Body": "STOP"}, timeout=30)
        assert r.status_code == 200
        assert "<Response>" in r.text and "xml" in r.headers.get("content-type", "")
        _, meta = outbox_for(tokens, "none")
        assert any(o["phone"] == RECIPIENT_PHONE for o in meta["optouts"]), meta["optouts"]

        # new consented job -> assigned SMS should be blocked_optout
        job = book_job(tokens, created_job_ids, consent=True, title_suffix=" optout")
        jid = job["id"]
        r = accept_as_driver(tokens, jid)
        assert r.status_code == 200, r.text[:300]
        time.sleep(1)
        msgs, _ = outbox_for(tokens, jid)
        assert len(msgs) == 1 and msgs[0]["status"] == "blocked_optout", msgs

    def test_start_removes_optout(self, tokens):
        r = requests.post(f"{API}/sms/twilio-webhook",
                          data={"From": RECIPIENT_PHONE, "Body": "START"}, timeout=30)
        assert r.status_code == 200
        _, meta = outbox_for(tokens, "none")
        assert not any(o["phone"] == RECIPIENT_PHONE for o in meta["optouts"])

    def test_admin_optout_add_remove(self, tokens):
        phone = "+14165550123"
        r = requests.post(f"{API}/admin/sms-optouts", headers=H(tokens["admin"]),
                          json={"phone": "416-555-0123", "action": "add"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["phone"] == phone
        _, meta = outbox_for(tokens, "none")
        assert any(o["phone"] == phone for o in meta["optouts"])
        r = requests.post(f"{API}/admin/sms-optouts", headers=H(tokens["admin"]),
                          json={"phone": phone, "action": "remove"}, timeout=30)
        assert r.status_code == 200
        _, meta = outbox_for(tokens, "none")
        assert not any(o["phone"] == phone for o in meta["optouts"])

    def test_admin_optout_invalid_inputs(self, tokens):
        r = requests.post(f"{API}/admin/sms-optouts", headers=H(tokens["admin"]),
                          json={"phone": "123", "action": "add"}, timeout=30)
        assert r.status_code == 422, r.status_code
        r = requests.post(f"{API}/admin/sms-optouts", headers=H(tokens["admin"]),
                          json={"phone": "+14165550123", "action": "bogus"}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_outbox_requires_staff(self, tokens):
        r = requests.get(f"{API}/admin/sms-outbox", headers=H(tokens["facility"]), timeout=30)
        assert r.status_code == 403, r.status_code
        r = requests.get(f"{API}/admin/sms-outbox", timeout=30)
        assert r.status_code in (401, 403), r.status_code
        r = requests.get(f"{API}/admin/sms-outbox", headers=H(tokens["dispatcher"]), timeout=30)
        assert r.status_code == 200, r.text[:200]


# ---- Public confirmation link ----
class TestConfirmLink:
    token = None
    job_id = None

    def test_get_info_no_auth(self, tokens):
        assert TestConfirmLink.token, "no confirm token captured (SMS flow test must run first)"
        r = requests.get(f"{API}/public/confirm/{TestConfirmLink.token}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["title"]
        assert d["facility_name"] and d["facility_name"] != "Your healthcare provider"
        assert d["driver_first_name"]
        assert d["delivered_at"]
        assert d["confirmed_at"] is None

    def test_bad_token_404(self):
        r = requests.get(f"{API}/public/confirm/not-a-real-token", timeout=30)
        assert r.status_code == 404
        r = requests.post(f"{API}/public/confirm/not-a-real-token", json={"rating": 5}, timeout=30)
        assert r.status_code == 404

    def test_confirm_with_rating(self, tokens):
        tok = TestConfirmLink.token
        r = requests.post(f"{API}/public/confirm/{tok}", json={"rating": 5, "comment": "TEST_QA great service"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["confirmed"] is True and d["rating_saved"] is True

        info = requests.get(f"{API}/public/confirm/{tok}", timeout=30).json()
        assert info["confirmed_at"], "recipient_confirmed_at not persisted"
        assert info["already_reviewed"] is True

        # review created for driver with reviewer 'Delivery recipient'
        me = requests.get(f"{API}/auth/me", headers=H(tokens["driver"]), timeout=30).json()
        rv = requests.get(f"{API}/drivers/{me['id']}/reviews", timeout=30)
        if rv.status_code != 200:
            rv = requests.get(f"{API}/reviews?driver_id={me['id']}", headers=H(tokens["admin"]), timeout=30)
        assert rv.status_code == 200, f"reviews fetch failed {rv.status_code} {rv.text[:200]}"
        body = rv.json()
        reviews = body if isinstance(body, list) else body.get("reviews", [])
        mine = [x for x in reviews if x.get("job_id") == TestConfirmLink.job_id]
        assert mine, f"recipient review not found for job {TestConfirmLink.job_id}"
        assert mine[0]["rating"] == 5
        assert mine[0].get("reviewer_name") == "Delivery recipient"

    def test_second_confirm_no_duplicate(self):
        r = requests.post(f"{API}/public/confirm/{TestConfirmLink.token}", json={"rating": 4}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"confirmed": True, "rating_saved": False}

    def test_facility_owner_notified_recipient_confirmed(self, tokens):
        r = requests.get(f"{API}/notifications", headers=H(tokens["facility"]), timeout=30)
        assert r.status_code == 200
        notifs = r.json()["notifications"]
        match = [n for n in notifs if n.get("type") == "recipient_confirmed" and n.get("job_id") == TestConfirmLink.job_id]
        assert match, f"facility owner not notified of recipient_confirmed; types={[n.get('type') for n in notifs][:10]}"


# ---- Notifications API ----
class TestNotificationsApi:
    def test_requires_auth(self):
        r = requests.get(f"{API}/notifications", timeout=30)
        assert r.status_code in (401, 403)

    def test_own_items_only(self, tokens):
        fac = requests.get(f"{API}/notifications", headers=H(tokens["facility"]), timeout=30).json()
        drv = requests.get(f"{API}/notifications", headers=H(tokens["driver"]), timeout=30).json()
        fac_ids = {n["id"] for n in fac["notifications"]}
        drv_ids = {n["id"] for n in drv["notifications"]}
        assert not (fac_ids & drv_ids), "notifications leaking across users"
        fac_me = requests.get(f"{API}/auth/me", headers=H(tokens["facility"]), timeout=30).json()
        assert all(n["user_id"] == fac_me["id"] for n in fac["notifications"] if "user_id" in n)

    def test_facility_notified_on_lifecycle(self, tokens):
        notifs = requests.get(f"{API}/notifications", headers=H(tokens["facility"]), timeout=30).json()["notifications"]
        types = {n.get("type") for n in notifs}
        for expected in ("driver_assigned", "picked_up", "delivered"):
            assert expected in types, f"missing facility notification '{expected}'; got {types}"

    def test_mark_specific_and_all_read(self, tokens):
        tok = tokens["facility"]
        data = requests.get(f"{API}/notifications", headers=H(tok), timeout=30).json()
        unread_items = [n for n in data["notifications"] if not n.get("read")]
        if unread_items:
            r = requests.post(f"{API}/notifications/read", headers=H(tok),
                              json={"ids": [unread_items[0]["id"]]}, timeout=30)
            assert r.status_code == 200 and r.json()["marked"] >= 1
            after = requests.get(f"{API}/notifications", headers=H(tok), timeout=30).json()
            target = [n for n in after["notifications"] if n["id"] == unread_items[0]["id"]][0]
            assert target["read"] is True
        r = requests.post(f"{API}/notifications/read", headers=H(tok), json={"all": True}, timeout=30)
        assert r.status_code == 200
        after = requests.get(f"{API}/notifications", headers=H(tok), timeout=30).json()
        assert after["unread"] == 0, after["unread"]

    def test_mark_read_validation(self, tokens):
        r = requests.post(f"{API}/notifications/read", headers=H(tokens["driver"]), json={}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_driver_job_offer_notification(self, tokens, created_job_ids):
        """Dispatcher offers a job to driver1 -> driver gets job_offer notification."""
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" offer")
        drv = requests.get(f"{API}/auth/me", headers=H(tokens["driver"]), timeout=30).json()
        # facility bookings land already in 'offered'; move to open pool first so status actually changes
        requests.put(f"{API}/jobs/{job['id']}", headers=H(tokens["dispatcher"]), timeout=30,
                     json={"status": "open"})
        r = requests.put(f"{API}/jobs/{job['id']}", headers=H(tokens["dispatcher"]), timeout=30,
                         json={"status": "offered", "assigned_driver_id": drv["id"]})
        assert r.status_code == 200, f"offer failed {r.status_code} {r.text[:300]}"
        time.sleep(1)
        notifs = requests.get(f"{API}/notifications", headers=H(tokens["driver"]), timeout=30).json()["notifications"]
        assert any(n.get("type") == "job_offer" and n.get("job_id") == job["id"] for n in notifs), \
            f"driver not notified of offer; types={[n.get('type') for n in notifs][:10]}"

    def test_driver_job_offer_when_assigned_to_pool_job(self, tokens, created_job_ids):
        """Facility bookings start as 'open' pool jobs; a dispatcher assignment must fire job_offer."""
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" pool offer")
        assert job["status"] == "open"
        drv = requests.get(f"{API}/auth/me", headers=H(tokens["driver"]), timeout=30).json()
        r = requests.put(f"{API}/jobs/{job['id']}", headers=H(tokens["dispatcher"]), timeout=30,
                         json={"status": "offered", "assigned_driver_id": drv["id"]})
        assert r.status_code == 200, r.text[:300]
        time.sleep(1)
        notifs = requests.get(f"{API}/notifications", headers=H(tokens["driver"]), timeout=30).json()["notifications"]
        assert any(n.get("type") == "job_offer" and n.get("job_id") == job["id"] for n in notifs), \
            "driver received no job_offer notification when assigned to an already-'offered' pool job"

    def test_returned_event_notifies_dispatchers(self, tokens, created_job_ids):
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" returned")
        jid = job["id"]
        assert accept_as_driver(tokens, jid).status_code == 200
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                          json={"event_type": "pickup_confirmed",
                                "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
        assert r.status_code == 201, r.text[:300]
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                          json={"event_type": "delivery_attempted", "notes": "TEST_QA nobody home"})
        assert r.status_code == 201, r.text[:300]
        r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                          json={"event_type": "returned", "notes": "TEST_QA recipient unavailable"})
        assert r.status_code == 201, r.text[:300]
        time.sleep(1)
        notifs = requests.get(f"{API}/notifications?limit=100", headers=H(tokens["dispatcher"]), timeout=30).json()["notifications"]
        mine = [n for n in notifs if n.get("job_id") == jid]
        assert mine, "dispatchers not notified of returned job"
        assert any(n.get("type") == "job_returned" for n in mine)
        # every notification must carry renderable title/body (bell renders n.title / n.body)
        blank = [n for n in mine if not n.get("title") or not n.get("body")]
        assert not blank, f"notification(s) without title/body will render blank in the bell: {blank}"
        returned = [n for n in mine if n.get("type") == "job_returned"]
        assert len(returned) == 1, f"duplicate job_returned notifications for one return event: {len(returned)}"

    def test_driver_cancel_notifies_dispatchers(self, tokens, created_job_ids):
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" driver cancel")
        jid = job["id"]
        assert accept_as_driver(tokens, jid).status_code == 200
        r = requests.post(f"{API}/jobs/{jid}/cancel", headers=H(tokens["driver"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        time.sleep(1)
        notifs = requests.get(f"{API}/notifications?limit=100", headers=H(tokens["dispatcher"]), timeout=30).json()["notifications"]
        assert any(n.get("type") == "driver_cancelled" and n.get("job_id") == jid for n in notifs), \
            "dispatchers not notified of driver cancellation"

    def test_staff_cancel_notifies_dispatchers(self, tokens, created_job_ids):
        job = book_job(tokens, created_job_ids, consent=False, title_suffix=" cancel")
        r = requests.put(f"{API}/jobs/{job['id']}", headers=H(tokens["dispatcher"]), timeout=30,
                         json={"status": "cancelled"})
        assert r.status_code == 200, f"cancel failed {r.status_code} {r.text[:300]}"
        time.sleep(1)
        notifs = requests.get(f"{API}/notifications", headers=H(tokens["dispatcher"]), timeout=30).json()["notifications"]
        assert any(n.get("type") == "job_cancelled" and n.get("job_id") == job["id"] for n in notifs), \
            f"dispatchers not notified of cancel; types={[n.get('type') for n in notifs][:10]}"


# ---- Stale sweep ----
class TestStaleSweep:
    def test_stale_notifications_deduped(self, tokens):
        notifs = requests.get(f"{API}/notifications?limit=100", headers=H(tokens["dispatcher"]), timeout=30).json()["notifications"]
        stale = [n for n in notifs if n.get("type") == "stale_job"]
        keys = [(n.get("meta", {}).get("job_id"), n.get("meta", {}).get("status")) for n in stale]
        assert len(keys) == len(set(keys)), f"duplicate stale_job notifications: {keys}"
