"""Admin billing / commission engine tests (summary, invoices, driver-statements, CSV export)."""
import os
import re
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
MONTH = datetime.now(timezone.utc).strftime("%Y-%m")

CREDS = {
    "admin": ("gabrielosmanhamza@yahoo.com", "Admin@123"),
    "facility": ("facility1@test.com", "Facility@123"),
    "driver": ("driver1@test.com", "Driver@123"),
    "dispatcher": ("dispatcher1@test.com", "Dispatch@123"),
}


def login(role):
    email, pwd = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {role} failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token for {role}"
    return tok


@pytest.fixture(scope="session")
def tokens():
    return {r: login(r) for r in CREDS}


def hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def created_jobs():
    ids = []
    yield ids


@pytest.fixture(scope="session", autouse=True)
def cleanup(tokens, created_jobs):
    yield
    a = hdr(tokens["admin"])
    # restore override to null
    requests.put(f"{API}/facilities/{_facility_id(tokens)}", headers=a,
                 json={"commission_rate_override": None}, timeout=30)
    for jid in ids_snapshot(created_jobs):
        requests.delete(f"{API}/jobs/{jid}", headers=a, timeout=30)


def ids_snapshot(lst):
    return list(lst)


_fac_cache = {}


def _facility_id(tokens):
    if "id" not in _fac_cache:
        r = requests.get(f"{API}/facilities", headers=hdr(tokens["facility"]), timeout=30)
        assert r.status_code == 200, r.text
        facs = r.json()["facilities"]
        assert facs, "facility1 owns no facility"
        _fac_cache["id"] = facs[0]["id"]
    return _fac_cache["id"]


# ---------- RBAC & validation ----------
class TestBillingRBAC:
    @pytest.mark.parametrize("role", ["dispatcher", "driver", "facility"])
    @pytest.mark.parametrize("path", ["summary", "invoices", "driver-statements"])
    def test_non_admin_forbidden(self, tokens, role, path):
        r = requests.get(f"{API}/admin/billing/{path}?month={MONTH}", headers=hdr(tokens[role]), timeout=30)
        assert r.status_code == 403, f"{role} {path} -> {r.status_code}"

    def test_unauthenticated(self, tokens):
        r = requests.get(f"{API}/admin/billing/summary", timeout=30)
        assert r.status_code in (401, 403)

    def test_export_non_admin_token(self, tokens):
        r = requests.get(f"{API}/admin/billing/export", params={"month": MONTH, "report": "revenue", "auth": tokens["driver"]}, timeout=30)
        assert r.status_code == 403, r.status_code

    @pytest.mark.parametrize("bad", ["2026-13-01", "abcd", "2026/08", "26-08"])
    def test_invalid_month_422(self, tokens, bad):
        r = requests.get(f"{API}/admin/billing/summary", params={"month": bad}, headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 422, f"{bad} -> {r.status_code} {r.text[:200]}"


# ---------- Consistency ----------
class TestBillingConsistency:
    def test_summary_internal_consistency(self, tokens):
        r = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        k = d["kpis"]
        assert d["month"] == MONTH
        assert round(k["commission_earned"] + k["cancellation_fees"], 2) == k["platform_revenue"]
        assert round(sum(f["gross"] for f in d["by_facility"]), 2) == k["gross_delivery_value"]
        assert round(sum(x["gross"] for x in d["by_region"]), 2) == k["gross_delivery_value"]
        assert sum(f["trips"] for f in d["by_facility"]) == k["completed_trips"]
        assert sum(x["trips"] for x in d["by_region"]) == k["completed_trips"]

    def test_invoices_math(self, tokens):
        r = requests.get(f"{API}/admin/billing/invoices", params={"month": MONTH}, headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["hst_rate"] == 0.13
        for inv in d["invoices"]:
            assert inv["deliveries"] == len(inv["items"])
            assert round(sum(i["facility_charge"] for i in inv["items"]), 2) == inv["subtotal"]
            assert inv["hst"] == round(inv["subtotal"] * 0.13, 2)
            assert inv["total"] == round(inv["subtotal"] + inv["hst"], 2)
            assert round(sum(i["commission"] for i in inv["items"]), 2) == inv["commission_earned"]
            for i in inv["items"]:
                assert i["driver_net"] == round(i["facility_charge"] - i["commission"], 2)
                assert set(["commission_rate", "driver_name", "region", "job_id"]).issubset(i)
                assert "_id" not in i

    def test_statements_math(self, tokens):
        r = requests.get(f"{API}/admin/billing/driver-statements", params={"month": MONTH}, headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for s in d["statements"]:
            assert s["trips"] == len(s["items"])
            assert round(sum(i["driver_gross"] for i in s["items"]), 2) == s["gross"]
            assert round(sum(i["commission"] for i in s["items"]), 2) == s["commission"]
            assert round(sum(float(f["amount"]) for f in s["fee_items"]), 2) == s["cancellation_fees"]
            assert s["net_payable"] == round(s["gross"] - s["commission"] - s["cancellation_fees"], 2)
            for f in s["fee_items"]:
                assert "_id" not in f

    def test_summary_matches_invoices_and_statements(self, tokens):
        a = hdr(tokens["admin"])
        s = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=a, timeout=30).json()
        inv = requests.get(f"{API}/admin/billing/invoices", params={"month": MONTH}, headers=a, timeout=30).json()
        st = requests.get(f"{API}/admin/billing/driver-statements", params={"month": MONTH}, headers=a, timeout=30).json()
        assert round(sum(i["subtotal"] for i in inv["invoices"]), 2) == s["kpis"]["gross_delivery_value"]
        assert round(sum(i["commission_earned"] for i in inv["invoices"]), 2) == s["kpis"]["commission_earned"]
        assert round(sum(x["cancellation_fees"] for x in st["statements"]), 2) == s["kpis"]["cancellation_fees"]

    def test_driver1_has_cancellation_fee(self, tokens):
        st = requests.get(f"{API}/admin/billing/driver-statements", params={"month": MONTH}, headers=hdr(tokens["admin"]), timeout=30).json()
        d1 = [s for s in st["statements"] if s.get("email") == CREDS["driver"][0]]
        assert d1, "driver1 has no statement this month"
        assert d1[0]["cancellation_fees"] >= 15.0, d1[0]["cancellation_fees"]

    def test_empty_month(self, tokens):
        a = hdr(tokens["admin"])
        s = requests.get(f"{API}/admin/billing/summary", params={"month": "2019-01"}, headers=a, timeout=30)
        assert s.status_code == 200
        k = s.json()["kpis"]
        assert k == {"completed_trips": 0, "gross_delivery_value": 0, "commission_earned": 0,
                     "cancellation_fees": 0, "platform_revenue": 0}
        inv = requests.get(f"{API}/admin/billing/invoices", params={"month": "2019-01"}, headers=a, timeout=30).json()
        assert inv["invoices"] == []
        st = requests.get(f"{API}/admin/billing/driver-statements", params={"month": "2019-01"}, headers=a, timeout=30).json()
        assert st["statements"] == []


# ---------- E2E math ----------
def complete_job(tokens, created_jobs, price, title):
    fac_id = _facility_id(tokens)
    payload = {
        "title": title,
        "pickup_address": "455 Queen St W, Toronto",
        "delivery_address": "100 Bloor St W, Toronto",
        "pickup_city": "Toronto",
        "delivery_city": "Mississauga",
        "goods_type": "lab_samples",
        "item_category": "lab_sample",
        "urgency": "standard",
        "estimated_distance_km": 12.0,
        "distance_km": 12.0,
        "offered_price": price,
        "payout_amount": price,
        "facility_id": fac_id,
    }
    r = requests.post(f"{API}/jobs", headers=hdr(tokens["facility"]), json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create job {r.status_code} {r.text[:300]}"
    jid = r.json().get("id") or r.json().get("job", {}).get("id")
    assert jid
    created_jobs.append(jid)
    dh = hdr(tokens["driver"])
    ra = requests.post(f"{API}/jobs/{jid}/accept", headers=dh, timeout=30)
    assert ra.status_code in (200, 201), f"accept {ra.status_code} {ra.text[:300]}"
    rp = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
        "event_type": "pickup_confirmed",
        "checklist": {"label_confirmed": True, "item_count_confirmed": True, "cooler_confirmed": True},
        "gps_lat": 43.65, "gps_lng": -79.39}, timeout=30)
    assert rp.status_code in (200, 201), f"pickup {rp.status_code} {rp.text[:300]}"
    rd = requests.post(f"{API}/jobs/{jid}/custody-events", headers=dh, json={
        "event_type": "delivered", "recipient_name": "TEST Recipient",
        "evidence_url": "https://example.com/sig.png", "gps_lat": 43.6, "gps_lng": -79.6}, timeout=30)
    assert rd.status_code in (200, 201), f"deliver {rd.status_code} {rd.text[:300]}"
    return jid, rd.json().get("settlement")


class TestBillingE2E:
    def test_default_rate_20pct(self, tokens, created_jobs):
        a = hdr(tokens["admin"])
        before = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=a, timeout=30).json()["kpis"]
        jid, settlement = complete_job(tokens, created_jobs, 100.0, "TEST_billing_default")
        assert settlement and settlement["commission_charged"] == 20.0, settlement
        after = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=a, timeout=30).json()["kpis"]
        assert after["completed_trips"] == before["completed_trips"] + 1
        assert round(after["gross_delivery_value"] - before["gross_delivery_value"], 2) == 100.0
        assert round(after["commission_earned"] - before["commission_earned"], 2) == 20.0
        assert round(after["platform_revenue"] - before["platform_revenue"], 2) == 20.0

        inv = requests.get(f"{API}/admin/billing/invoices", params={"month": MONTH}, headers=a, timeout=30).json()
        item = next((i for iv in inv["invoices"] for i in iv["items"] if i["job_id"] == jid), None)
        assert item, "new job missing from invoices"
        assert item["facility_charge"] == 100.0
        assert item["commission"] == 20.0
        assert item["commission_rate"] == 0.20
        assert item["driver_net"] == 80.0
        assert item["region"] == "Mississauga"
        assert item["driver_name"]

        st = requests.get(f"{API}/admin/billing/driver-statements", params={"month": MONTH}, headers=a, timeout=30).json()
        s = next((x for x in st["statements"] if x.get("email") == CREDS["driver"][0]), None)
        assert s and any(i["job_id"] == jid for i in s["items"])

    def test_facility_override_10pct(self, tokens, created_jobs):
        a = hdr(tokens["admin"])
        fac_id = _facility_id(tokens)
        ro = requests.put(f"{API}/facilities/{fac_id}", headers=a, json={"commission_rate_override": 0.10}, timeout=30)
        assert ro.status_code == 200, ro.text[:300]
        assert ro.json().get("commission_rate_override") == 0.10
        try:
            jid, settlement = complete_job(tokens, created_jobs, 200.0, "TEST_billing_override")
            assert settlement["commission_charged"] == 20.0, settlement
            inv = requests.get(f"{API}/admin/billing/invoices", params={"month": MONTH}, headers=a, timeout=30).json()
            item = next((i for iv in inv["invoices"] for i in iv["items"] if i["job_id"] == jid), None)
            assert item, "override job missing from invoices"
            assert item["commission"] == 20.0
            assert item["commission_rate"] == 0.10
            assert item["driver_net"] == 180.0
        finally:
            rc = requests.put(f"{API}/facilities/{fac_id}", headers=a, json={"commission_rate_override": None}, timeout=30)
            assert rc.status_code == 200, rc.text[:300]
            assert rc.json().get("commission_rate_override") is None


# ---------- CSV export ----------
class TestBillingCSV:
    @pytest.mark.parametrize("report", ["revenue", "invoices", "driver_statements", "jobs"])
    def test_csv(self, tokens, report):
        r = requests.get(f"{API}/admin/billing/export", params={"month": MONTH, "report": report, "auth": tokens["admin"]}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "text/csv" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and f"meditrans-{report}-{MONTH}.csv" in cd, cd
        body = r.text
        assert "MediTrans Ontario" in body
        assert len(body.splitlines()) >= 3, body

    def test_jobs_csv_row_count_matches_summary(self, tokens):
        a = hdr(tokens["admin"])
        s = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=a, timeout=30).json()
        r = requests.get(f"{API}/admin/billing/export", params={"month": MONTH, "report": "jobs", "auth": tokens["admin"]}, timeout=60)
        rows = [l for l in r.text.splitlines() if l.strip()][2:]
        assert len(rows) == s["kpis"]["completed_trips"], f"{len(rows)} rows vs {s['kpis']['completed_trips']} trips"
        assert all(re.search(r"\d+%", row) for row in rows), rows[:3]

    def test_revenue_csv_totals(self, tokens):
        a = hdr(tokens["admin"])
        s = requests.get(f"{API}/admin/billing/summary", params={"month": MONTH}, headers=a, timeout=30).json()["kpis"]
        r = requests.get(f"{API}/admin/billing/export", params={"month": MONTH, "report": "revenue", "auth": tokens["admin"]}, timeout=60)
        lines = r.text.splitlines()
        vals = lines[2].split(",")
        assert int(vals[0]) == s["completed_trips"]
        assert float(vals[1]) == s["gross_delivery_value"]
        assert float(vals[2]) == s["commission_earned"]
        assert float(vals[4]) == s["platform_revenue"]

    def test_invoices_csv_matches_api(self, tokens):
        a = hdr(tokens["admin"])
        inv = requests.get(f"{API}/admin/billing/invoices", params={"month": MONTH}, headers=a, timeout=30).json()["invoices"]
        r = requests.get(f"{API}/admin/billing/export", params={"month": MONTH, "report": "invoices", "auth": tokens["admin"]}, timeout=60)
        rows = [l for l in r.text.splitlines() if l.strip()][2:]
        assert len(rows) == len(inv)
        for i, row in zip(inv, rows):
            assert f"{i['total']:.2f}" in row


# ---------- Regression on adjacent reports ----------
class TestBillingRegression:
    def test_facility_billing_still_works(self, tokens):
        r = requests.get(f"{API}/facility/billing", params={"month": MONTH}, headers=hdr(tokens["facility"]), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert "statement" in r.json() or "facility" in str(r.json())

    def test_driver_earnings_still_works(self, tokens):
        r = requests.get(f"{API}/earnings/stats", headers=hdr(tokens["driver"]), timeout=30)
        assert r.status_code == 200, r.text[:300]

    @pytest.mark.parametrize("path", ["admin/users", "admin/driver-verifications", "admin/facilities", "admin/jobs", "admin/ledger", "admin/stats"])
    def test_admin_tabs_endpoints(self, tokens, path):
        r = requests.get(f"{API}/{path}", headers=hdr(tokens["admin"]), timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
