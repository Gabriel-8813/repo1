"""Phase 2-4 marketplace money flow: delivery -> commission 'accrued' + driver_payout 'pending',
facility statement payment via Stripe Checkout, driver payouts, account deletion, CVOR optional, regressions.
Post-payment checks (TestAfterPayment) need /tmp/it25_session.txt written after a browser Stripe test checkout."""
import base64
import io
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

base_url = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
API = f"{base_url.rstrip('/')}/api"
benv = dotenv_values("/app/backend/.env")
DB = MongoClient(benv["MONGO_URL"])[benv["DB_NAME"]]
CREDS = {
    "driver": ("demo.driver@meditrans.ca", "DemoDriver#2026"),
    "facility": ("demo.facility@meditrans.ca", "DemoFacility#2026"),
    "admin": ("demo.admin@meditrans.ca", "DemoAdmin#2026"),
}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
MONTH = datetime.now(timezone.utc).strftime("%Y-%m")
SESSION_FILE = "/tmp/it25_session.txt"
STATE = {}


@pytest.fixture(scope="module")
def tok():
    out = {}
    for role, (e, p) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
        assert r.status_code == 200, f"{role} login {r.status_code}"
        out[role] = r.json()["access_token"]
        out[role + "_id"] = r.json()["user"]["id"]
    return out


def H(t, role):
    return {"Authorization": f"Bearer {t[role]}"}


# --- Money flow E2E: delivered -> 1 accrued commission + 1 pending driver_payout (net = gross - commission) ---
def test_delivery_creates_accrued_commission_and_pending_payout(tok):
    payload = {"recipient_name": "TEST_Money Recipient", "recipient_phone": "+14165550199",
               "dropoff_address": "100 Queen St W, Toronto, ON M5H 2N2", "item_count": 1,
               "item_category": "prescription", "handling_flags": [], "requested_pickup_time": "2026-12-01T10:00",
               "consent_data_handling": True, "recipient_sms_consent": False}
    r = requests.post(f"{API}/facility/requests", json=payload, headers=H(tok, "facility"), timeout=60)
    assert r.status_code == 201, r.text[:300]
    jid = r.json()["id"]
    assert requests.post(f"{API}/jobs/{jid}/accept", headers=H(tok, "driver"), timeout=30).status_code == 200
    r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tok, "driver"), timeout=30,
                      json={"event_type": "pickup_confirmed", "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
    assert r.status_code == 201, r.text
    r = requests.post(f"{API}/jobs/{jid}/delivery-evidence", headers=H(tok, "driver"), timeout=60,
                      files={"file": ("sig.png", io.BytesIO(PNG), "image/png")}, data={"kind": "signature"})
    assert r.status_code == 201, r.text
    ev = r.json()["evidence_url"]
    r = requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tok, "driver"), timeout=30,
                      json={"event_type": "delivered", "recipient_name": "TEST_Recv", "evidence_url": ev})
    assert r.status_code == 201, r.text
    s = r.json()["settlement"]
    gross = s["gross_earnings"]
    assert gross > 0
    assert round(s["net_earnings"], 2) == round(gross - s["commission_charged"], 2)
    comm = list(DB.ledger.find({"job_id": jid, "type": "commission"}, {"_id": 0}))
    pay = list(DB.ledger.find({"job_id": jid, "type": "driver_payout"}, {"_id": 0}))
    assert len(comm) == 1 and comm[0]["status"] == "accrued"
    assert len(pay) == 1 and pay[0]["status"] == "pending"
    assert round(pay[0]["amount"], 2) == round(gross - comm[0]["amount"], 2)
    fac = DB.facilities.find_one({"owner_user_id": tok["facility_id"]}, {"_id": 0, "commission_rate_override": 1})
    rate = fac.get("commission_rate_override") if fac and fac.get("commission_rate_override") is not None else 0.20
    assert round(comm[0]["amount"], 2) == round(gross * rate, 2)
    # no new 'owed' entry for driver
    assert DB.ledger.count_documents({"job_id": jid, "status": "owed"}) == 0
    STATE["job"] = jid
    STATE["payout_amount"] = pay[0]["amount"]


def test_driver_payouts_endpoint(tok):
    r = requests.get(f"{API}/driver/payouts", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["pending_total"] > 0 and isinstance(d["payouts"], list)
    assert d["connect_ready"] is False
    if STATE.get("job"):
        assert any(p["job_id"] == STATE["job"] and p["status"] == "pending" for p in d["payouts"])


def test_driver_balance_does_not_include_accrued(tok):
    r = requests.get(f"{API}/driver/balance", headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 200
    owed_db = sum(e["amount"] for e in DB.ledger.find({"driver_id": tok["driver_id"], "status": "owed"}))
    assert round(r.json()["owed"], 2) == round(owed_db, 2)


# --- Facility statement & pay endpoint ---
def test_facility_billing_unpaid_and_pay_returns_checkout(tok):
    r = requests.get(f"{API}/facility/billing?month={MONTH}", headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 200
    st = r.json()
    if st.get("paid"):
        pytest.skip("statement already paid this month")
    assert st["total"] > 0 and st["paid"] is False
    assert any(i["job_id"] == STATE.get("job") for i in st["items"])
    r = requests.post(f"{API}/facility/billing/pay", json={"month": MONTH, "origin_url": base_url},
                      headers=H(tok, "facility"), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["checkout_url"].startswith("https://checkout.stripe.com")
    assert d["session_id"].startswith("cs_test_")
    assert round(d["amount"], 2) == round(st["due_total"], 2)
    with open("/tmp/it25_checkout.txt", "w") as f:
        f.write(d["session_id"] + "\n" + d["checkout_url"])


def test_pay_rbac_and_validation(tok):
    r = requests.post(f"{API}/facility/billing/pay", json={"month": MONTH, "origin_url": base_url}, headers=H(tok, "driver"), timeout=30)
    assert r.status_code == 403
    r = requests.post(f"{API}/facility/billing/pay", json={"month": "2026/11", "origin_url": base_url}, headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 422
    r = requests.post(f"{API}/facility/billing/pay", json={"month": "2001-01", "origin_url": base_url}, headers=H(tok, "facility"), timeout=30)
    assert r.status_code == 400


# --- Compliance text / permits ---
def test_permits_cvor_optional():
    r = requests.get(f"{API}/permits", timeout=30)
    assert r.status_code == 200
    cvor = next(p for p in r.json()["permits"] if p["id"] == "cvor")
    assert cvor["required"] is False, f"CVOR returned required={cvor['required']}"


# --- Account deletion (disposable user) ---
def test_account_delete_flow():
    email = f"test_del_{uuid.uuid4().hex[:8]}@example.com"
    pw = "TestDel#2026"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "full_name": "TEST_Delete Me",
                      "phone": "+14165550123", "role": "facility", "privacy_policy_accepted": True}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    t = r.json().get("access_token") or requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert requests.post(f"{API}/auth/delete-account", json={"password": "wrong-pass"}, headers=h, timeout=30).status_code == 400
    r = requests.post(f"{API}/auth/delete-account", json={"password": pw}, headers=h, timeout=30)
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    assert requests.get(f"{API}/auth/me", headers=h, timeout=30).status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30).status_code in (401, 403)
    u = DB.users.find_one({"email": {"$regex": "^deleted-"}, "full_name": "Deleted User", "deleted_at": {"$exists": True}}, sort=[("deleted_at", -1)])
    assert u and u["status"] == "deleted" and u.get("phone") is None


def test_admin_cannot_self_delete(tok):
    r = requests.post(f"{API}/auth/delete-account", json={"password": CREDS["admin"][1]}, headers=H(tok, "admin"), timeout=30)
    assert r.status_code == 400


# --- Regression ---
def test_regression_endpoints(tok):
    assert requests.get(f"{API}/earnings/stats", headers=H(tok, "driver"), timeout=30).status_code == 200
    assert requests.get(f"{API}/earnings", headers=H(tok, "driver"), timeout=30).status_code == 200


# --- After browser checkout ---
@pytest.mark.skipif(not os.path.exists(SESSION_FILE), reason="no paid session yet")
class TestAfterPayment:
    def test_status_paid_and_settlement(self, tok):
        sid = open(SESSION_FILE).read().strip()
        d = None
        for _ in range(10):
            r = requests.get(f"{API}/payments/status/{sid}", headers=H(tok, "facility"), timeout=30)
            assert r.status_code == 200, r.text
            d = r.json()
            if d["payment_status"] == "paid":
                break
            time.sleep(3)
        assert d["payment_status"] == "paid"
        st = requests.get(f"{API}/facility/billing?month={MONTH}", headers=H(tok, "facility"), timeout=30).json()
        assert st["paid_at"], "no facility payment recorded"
        paid_items = [i for i in st["items"] if i.get("paid")]
        assert paid_items, "no statement items marked paid after payment"
        if all(i.get("paid") for i in st["items"]):
            assert st["paid"] is True
        else:
            assert st["paid"] is False  # newer unpaid jobs keep statement open
        job_ids = [i["job_id"] for i in paid_items]
        for jid in job_ids:
            j = DB.jobs.find_one({"id": jid}, {"_id": 0, "facility_paid": 1, "facility_id": 1})
            assert j.get("facility_paid") is True, f"job {jid} not facility_paid (facility_id={j.get('facility_id')})"
            assert DB.ledger.count_documents({"job_id": jid, "type": "commission", "status": "accrued"}) == 0
            for p in DB.ledger.find({"job_id": jid, "type": "driver_payout"}):
                assert p["status"] in ("pending", "paid")
                if p["status"] == "paid":
                    assert p.get("stripe_transfer_id")
        assert DB.facility_payments.count_documents({"session_id": sid, "status": "paid"}) == 1

    def test_repay_rejected(self, tok):
        st = requests.get(f"{API}/facility/billing?month={MONTH}", headers=H(tok, "facility"), timeout=30).json()
        r = requests.post(f"{API}/facility/billing/pay", json={"month": MONTH, "origin_url": base_url},
                          headers=H(tok, "facility"), timeout=30)
        if any(not i["paid"] for i in st["items"]):
            # new unpaid deliveries since last payment: repay allowed, but only for the remainder
            assert r.status_code == 200, r.text
            assert round(r.json()["amount"], 2) == round(st["due_total"], 2)
        else:
            assert r.status_code == 400 and "already" in r.text.lower()

    def test_status_poll_idempotent(self, tok):
        sid = open(SESSION_FILE).read().strip()
        requests.get(f"{API}/payments/status/{sid}", headers=H(tok, "facility"), timeout=30)
        assert DB.facility_payments.count_documents({"session_id": sid}) == 1
