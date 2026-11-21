"""Active Delivery flow — custody event stage machine, delivery evidence,
returns + notifications, and legacy complete/tips/reviews regressions."""
import base64
import io
import os
import uuid

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
    "driver": ("driver1@test.com", "Driver@123"),
    "driver2": ("newdriver@test.com", "NewDriver@123"),
    "facility": ("facility1@test.com", "Facility@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
}

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def login(role):
    email, password = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {role} failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    return data["access_token"], data["user"]


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role in CREDS:
        out[role] = login(role)
    return out


def hdr(tokens, role):
    return {"Authorization": f"Bearer {tokens[role][0]}"}


@pytest.fixture(scope="module")
def facility_id(tokens):
    r = requests.get(f"{API}/facilities", headers=hdr(tokens, "facility"), timeout=30)
    assert r.status_code == 200, r.text[:300]
    facs = r.json().get("facilities") or r.json()
    assert facs, "no facilities available"
    return facs[0]["id"]


@pytest.fixture(scope="module")
def created_jobs():
    return []


def make_job(tokens, facility_id, created_jobs, flags=None, cold=False, price=25.0, title="TEST_ Active Delivery"):
    payload = {
        "title": title,
        "pickup_address": "123 Queen St W, Toronto, ON M5H 2M9",
        "dropoff_address": "500 University Ave, Toronto, ON M5G 1X8",
        "pickup_city": "Toronto",
        "delivery_city": "Toronto",
        "item_category": "lab_sample",
        "handling_flags": flags or [],
        "temperature_controlled": cold,
        "offered_price": price,
        "distance_km": 6.0,
        "facility_id": facility_id,
    }
    r = requests.post(f"{API}/jobs", json=payload, headers=hdr(tokens, "facility"), timeout=30)
    assert r.status_code in (200, 201), f"job create failed {r.status_code} {r.text[:400]}"
    job = r.json()
    created_jobs.append(job["id"])
    return job["id"]


def accept(tokens, job_id):
    r = requests.post(f"{API}/jobs/{job_id}/accept", headers=hdr(tokens, "driver"), timeout=30)
    assert r.status_code in (200, 201), f"accept failed {r.status_code} {r.text[:300]}"
    return r


def custody(tokens, job_id, role="driver", **payload):
    return requests.post(f"{API}/jobs/{job_id}/custody-events", json=payload,
                         headers=hdr(tokens, role), timeout=60)


def get_job(tokens, job_id, role="driver"):
    r = requests.get(f"{API}/jobs/{job_id}", headers=hdr(tokens, role), timeout=30)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def upload_evidence(tokens, job_id, role="driver", kind="signature", data=None, filename="sig.png",
                    content_type="image/png"):
    files = {"file": (filename, io.BytesIO(data if data is not None else PNG_BYTES), content_type)}
    return requests.post(f"{API}/jobs/{job_id}/delivery-evidence", files=files, data={"kind": kind},
                         headers=hdr(tokens, role), timeout=60)


@pytest.fixture(scope="module", autouse=True)
def cleanup(tokens, created_jobs):
    yield
    for jid in created_jobs:
        requests.delete(f"{API}/jobs/{jid}", headers=hdr(tokens, "admin"), timeout=30)


# ---------- Stage machine: pickup_confirmed ----------
class TestPickupStage:
    def test_pickup_requires_accepted_status(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        # not accepted yet -> driver not assigned => 403
        r = custody(tokens, job_id, event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 403, f"expected 403 for unassigned driver, got {r.status_code} {r.text[:300]}"

    def test_pickup_checklist_missing_items(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, flags=["cold_chain"])
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="pickup_confirmed", checklist={})
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        detail = r.json()["detail"]
        assert "label" in detail and "item count" in detail and "cooler" in detail, detail

        # only cooler missing on cold chain job
        r = custody(tokens, job_id, event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 400
        assert "cooler" in r.json()["detail"]

        # complete checklist succeeds
        r = custody(tokens, job_id, event_type="pickup_confirmed", gps_lat=43.65, gps_lng=-79.38,
                    checklist={"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True})
        assert r.status_code == 201, r.text[:300]
        body = r.json()
        assert body["event_type"] == "pickup_confirmed"
        assert body["job_status"] == "picked_up"
        assert body["gps_lat"] == 43.65
        assert body["timestamp"]
        assert "_id" not in body
        job = get_job(tokens, job_id)
        assert job["status"] == "picked_up"
        assert job.get("picked_up_at")

    def test_cooler_not_required_for_non_cold_job(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, flags=["fragile"])
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 201, r.text[:300]
        assert get_job(tokens, job_id)["status"] == "picked_up"

    def test_temperature_controlled_requires_cooler(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, cold=True)
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 400, f"temperature_controlled job should demand cooler: {r.status_code}"
        assert "cooler" in r.json()["detail"]

    def test_double_pickup_confirm_rejected(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        ok = {"label_confirmed": True, "item_count_confirmed": True}
        assert custody(tokens, job_id, event_type="pickup_confirmed", checklist=ok).status_code == 201
        r = custody(tokens, job_id, event_type="pickup_confirmed", checklist=ok)
        assert r.status_code == 400, r.status_code


# ---------- Stage machine: in_transit_ping ----------
class TestTransitStage:
    def test_ping_requires_picked_up(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="in_transit_ping")
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_first_ping_flips_to_in_transit(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        custody(tokens, job_id, event_type="pickup_confirmed",
                checklist={"label_confirmed": True, "item_count_confirmed": True})
        r = custody(tokens, job_id, event_type="in_transit_ping", gps_lat=43.7, gps_lng=-79.4)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["job_status"] == "in_transit"
        assert get_job(tokens, job_id)["status"] == "in_transit"
        # second ping stays in_transit
        r2 = custody(tokens, job_id, event_type="in_transit_ping")
        assert r2.status_code == 201
        assert r2.json()["job_status"] == "in_transit"
        events = requests.get(f"{API}/jobs/{job_id}/custody-events", headers=hdr(tokens, "driver"),
                              timeout=30).json()["custody_events"]
        pings = [e for e in events if e["event_type"] == "in_transit_ping"]
        assert len(pings) == 2


# ---------- Delivery evidence upload/serve ----------
class TestDeliveryEvidence:
    def test_evidence_rbac_and_serve(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)

        # bad kind -> 422
        r = upload_evidence(tokens, job_id, kind="selfie")
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

        # other driver -> 403
        r = upload_evidence(tokens, job_id, role="driver2")
        assert r.status_code == 403, f"other driver should be 403, got {r.status_code}"

        # facility -> 403
        r = upload_evidence(tokens, job_id, role="facility")
        assert r.status_code == 403, f"facility should be 403, got {r.status_code}"

        # assigned driver -> 201
        r = upload_evidence(tokens, job_id, kind="signature")
        assert r.status_code == 201, f"{r.status_code} {r.text[:400]}"
        body = r.json()
        assert body["kind"] == "signature"
        assert body["evidence_url"] == f"/api/delivery-evidence/{body['evidence_id']}/file"
        ev_url = f"{BASE_URL}{body['evidence_url']}"

        # driver can fetch bytes
        g = requests.get(ev_url, headers=hdr(tokens, "driver"), timeout=30)
        assert g.status_code == 200, f"{g.status_code} {g.text[:200]}"
        assert g.content == PNG_BYTES
        assert "image" in g.headers.get("content-type", "")

        # staff (dispatcher) + facility owner can fetch
        for role in ("dispatcher", "facility", "admin"):
            g = requests.get(ev_url, headers=hdr(tokens, role), timeout=30)
            assert g.status_code == 200, f"{role} fetch got {g.status_code}"

        # unrelated driver -> 403
        g = requests.get(ev_url, headers=hdr(tokens, "driver2"), timeout=30)
        assert g.status_code == 403, f"unrelated driver got {g.status_code}"

        # ?auth= query token works, bad token 401
        g = requests.get(ev_url, params={"auth": tokens["driver"][0]}, timeout=30)
        assert g.status_code == 200, g.status_code
        g = requests.get(ev_url, params={"auth": "not-a-jwt"}, timeout=30)
        assert g.status_code == 401, g.status_code

        # unknown evidence id -> 404
        g = requests.get(f"{API}/delivery-evidence/{uuid.uuid4()}/file", headers=hdr(tokens, "driver"), timeout=30)
        assert g.status_code == 404, g.status_code

    def test_id_photo_kind(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, flags=["id_required"])
        accept(tokens, job_id)
        r = upload_evidence(tokens, job_id, kind="id_photo", filename="id.png")
        assert r.status_code == 201, r.text[:300]
        assert r.json()["kind"] == "id_photo"


# ---------- Delivered event + settlement ----------
class TestDeliveredStage:
    def test_delivered_validations_and_settlement(self, tokens, facility_id, created_jobs):
        price = 42.5
        job_id = make_job(tokens, facility_id, created_jobs, flags=["signature_required"], price=price)
        accept(tokens, job_id)

        # before pickup -> 400
        r = custody(tokens, job_id, event_type="delivered", recipient_name="Jane", evidence_url="/x")
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

        custody(tokens, job_id, event_type="pickup_confirmed",
                checklist={"label_confirmed": True, "item_count_confirmed": True})
        custody(tokens, job_id, event_type="in_transit_ping")

        # missing recipient_name -> 422
        r = custody(tokens, job_id, event_type="delivered", evidence_url="/x")
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

        # missing evidence -> 422 with door message
        r = custody(tokens, job_id, event_type="delivered", recipient_name="Jane Doe")
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"
        assert "never be left at the door" in str(r.json()["detail"])

        # driver trips before (admin view of driver record)
        driver_uid = tokens["driver"][1]["id"]
        rec = requests.get(f"{API}/drivers/{driver_uid}/record", headers=hdr(tokens, "admin"), timeout=30)
        trips_before = None
        if rec.status_code == 200:
            body_rec = rec.json()
            trips_before = (body_rec.get("driver") or body_rec).get("total_trips")

        ev = upload_evidence(tokens, job_id, kind="signature").json()
        r = custody(tokens, job_id, event_type="delivered", recipient_name="Jane Doe",
                    recipient_relationship="daughter", evidence_url=ev["evidence_url"],
                    gps_lat=43.66, gps_lng=-79.39)
        assert r.status_code == 201, r.text[:400]
        body = r.json()
        assert body["job_status"] == "delivered"
        s = body["settlement"]
        assert s["gross_earnings"] == price
        assert s["commission_charged"] == round(price * 0.20, 2), s
        assert s["net_earnings"] == round(price - s["commission_charged"], 2)

        job = get_job(tokens, job_id)
        assert job["status"] == "delivered"
        assert job.get("delivered_at")

        # earnings persisted
        earnings = requests.get(f"{API}/earnings", headers=hdr(tokens, "driver"), timeout=30).json()["earnings"]
        assert any(e["job_id"] == job_id and e["amount"] == price for e in earnings), "earnings row missing"

        # ledger commission owed
        led = requests.get(f"{API}/driver/balance", headers=hdr(tokens, "driver"), timeout=30)
        assert led.status_code == 200, led.text[:200]
        entries = led.json().get("entries") or []
        match = [e for e in entries if e.get("job_id") == job_id and e.get("type") == "commission"]
        assert match, "commission ledger entry missing"
        assert match[0]["status"] == "owed"
        assert match[0]["amount"] == s["commission_charged"]

        # total_trips incremented
        if trips_before is not None:
            after = requests.get(f"{API}/drivers/{driver_uid}/record", headers=hdr(tokens, "admin"), timeout=30).json()
            trips_after = (after.get("driver") or after).get("total_trips")
            assert trips_after == trips_before + 1, f"{trips_before} -> {trips_after}"

        # custody trail
        events = requests.get(f"{API}/jobs/{job_id}/custody-events", headers=hdr(tokens, "driver"),
                              timeout=30).json()["custody_events"]
        types = [e["event_type"] for e in events]
        assert types == ["pickup_confirmed", "in_transit_ping", "delivered"], types
        assert events[-1]["evidence_url"] == ev["evidence_url"]
        assert events[-1]["recipient_name"] == "Jane Doe"
        assert events[-1]["recipient_relationship"] == "daughter"

        # delivered job can be reviewed + tipped
        info = requests.get(f"{API}/reviews/info/{job_id}", timeout=30)
        assert info.status_code == 200, f"review info on delivered job: {info.status_code} {info.text[:200]}"
        rev = requests.post(f"{API}/reviews/{job_id}", json={"rating": 5, "comment": "TEST_ great",
                                                             "reviewer_name": "TEST_ Customer"}, timeout=30)
        assert rev.status_code in (200, 201), f"{rev.status_code} {rev.text[:300]}"
        assert rev.json()["review"]["rating"] == 5

        tip = requests.post(f"{API}/tips/checkout/{job_id}",
                            json={"amount": 5.0, "origin_url": BASE_URL}, timeout=60)
        assert tip.status_code != 400 or "completed trips" not in tip.text, \
            f"tip rejected for delivered job: {tip.status_code} {tip.text[:300]}"

        # append-only
        assert requests.put(f"{API}/custody-events/{events[0]['id']}", headers=hdr(tokens, "driver"),
                            timeout=30).status_code == 405
        assert requests.delete(f"{API}/custody-events/{events[0]['id']}", headers=hdr(tokens, "driver"),
                               timeout=30).status_code == 405

    def test_no_events_after_delivered(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, price=10.0)
        accept(tokens, job_id)
        custody(tokens, job_id, event_type="pickup_confirmed",
                checklist={"label_confirmed": True, "item_count_confirmed": True})
        ev = upload_evidence(tokens, job_id).json()
        assert custody(tokens, job_id, event_type="delivered", recipient_name="A",
                       evidence_url=ev["evidence_url"]).status_code == 201
        for et in ("in_transit_ping", "delivery_attempted", "delivered"):
            r = custody(tokens, job_id, event_type=et, recipient_name="A", evidence_url=ev["evidence_url"])
            assert r.status_code == 400, f"{et} after delivered should 400, got {r.status_code}"


# ---------- Return / exception path + notifications ----------
class TestReturnFlow:
    def test_return_requires_attempt_and_notifies(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, flags=["id_required"], price=58.0)
        accept(tokens, job_id)
        custody(tokens, job_id, event_type="pickup_confirmed",
                checklist={"label_confirmed": True, "item_count_confirmed": True})

        # returned without prior attempt -> 400
        r = custody(tokens, job_id, event_type="returned")
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert "delivery attempt" in r.json()["detail"]

        r = custody(tokens, job_id, event_type="delivery_attempted", notes="TEST_ nobody home")
        assert r.status_code == 201, r.text[:300]
        assert r.json()["job_status"] in ("picked_up", "in_transit")

        r = custody(tokens, job_id, event_type="returned", gps_lat=43.64, gps_lng=-79.4)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["job_status"] == "returned"
        assert get_job(tokens, job_id)["status"] == "returned"

        # notifications for facility owner + dispatcher
        for role in ("facility", "dispatcher"):
            n = requests.get(f"{API}/notifications", headers=hdr(tokens, role), timeout=30)
            assert n.status_code == 200, n.text[:200]
            data = n.json()
            notes = [x for x in data["notifications"] if x["job_id"] == job_id and x["type"] == "job_returned"]
            assert notes, f"{role} missing job_returned notification"
            assert notes[0]["read"] is False
            assert isinstance(data["unread"], int) and data["unread"] >= 1
            # mark read
            pr = requests.put(f"{API}/notifications/{notes[0]['id']}/read", headers=hdr(tokens, role), timeout=30)
            assert pr.status_code == 200, pr.text[:200]
            n2 = requests.get(f"{API}/notifications", headers=hdr(tokens, role), timeout=30).json()
            assert next(x for x in n2["notifications"] if x["id"] == notes[0]["id"])["read"] is True

        # other user cannot mark someone else's notification read
        note_id = [x for x in requests.get(f"{API}/notifications", headers=hdr(tokens, "facility"),
                                           timeout=30).json()["notifications"]
                   if x["job_id"] == job_id][0]["id"]
        r = requests.put(f"{API}/notifications/{note_id}/read", headers=hdr(tokens, "driver"), timeout=30)
        assert r.status_code == 404, f"cross-user notification read got {r.status_code}"

    def test_delivery_attempted_requires_active_delivery(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="delivery_attempted")
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"


# ---------- Legacy complete regression ----------
class TestLegacyComplete:
    def test_complete_from_accepted_settles(self, tokens, facility_id, created_jobs):
        price = 30.0
        job_id = make_job(tokens, facility_id, created_jobs, price=price)
        accept(tokens, job_id)
        r = requests.post(f"{API}/jobs/{job_id}/complete", headers=hdr(tokens, "driver"), timeout=60)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["job"]["status"] == "completed"
        assert body["gross_earnings"] == price
        assert body["commission_charged"] == round(price * 0.2, 2)
        assert body["net_earnings"] == round(price * 0.8, 2)
        assert get_job(tokens, job_id)["status"] == "completed"

    def test_complete_from_in_transit(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs, price=20.0)
        accept(tokens, job_id)
        custody(tokens, job_id, event_type="pickup_confirmed",
                checklist={"label_confirmed": True, "item_count_confirmed": True})
        custody(tokens, job_id, event_type="in_transit_ping")
        r = requests.post(f"{API}/jobs/{job_id}/complete", headers=hdr(tokens, "driver"), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["job"]["status"] == "completed"


# ---------- RBAC / misc ----------
class TestCustodyRbac:
    def test_facility_cannot_create_custody_event(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        r = custody(tokens, job_id, role="facility", event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_invalid_event_type_and_missing_job(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        accept(tokens, job_id)
        r = custody(tokens, job_id, event_type="teleported")
        assert r.status_code in (400, 422), r.status_code
        r = custody(tokens, str(uuid.uuid4()), event_type="pickup_confirmed",
                    checklist={"label_confirmed": True, "item_count_confirmed": True})
        assert r.status_code == 404, r.status_code

    def test_unauthenticated_blocked(self, tokens, facility_id, created_jobs):
        job_id = make_job(tokens, facility_id, created_jobs)
        r = requests.post(f"{API}/jobs/{job_id}/custody-events", json={"event_type": "pickup_confirmed"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code
