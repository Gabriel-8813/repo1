"""Seed data for frontend notification/SMS UI tests.
Creates: (a) delivered job with consent -> prints confirm token, (b) picked_up job for driver1
so the Active Delivery page shows the 'arriving soon' button.
Prints job ids for cleanup."""
import io
import sys

sys.path.insert(0, "/app/backend")
import requests
from tests.test_notifications_sms import API, H, _login

tokens = {r: _login(r) for r in ("admin", "driver", "facility")}


def book(consent, suffix):
    payload = {
        "recipient_name": f"TEST_QA UI {suffix}",
        "dropoff_address": "100 Queen St W, Toronto, ON",
        "recipient_phone": "+14165559999",
        "item_count": 1,
        "item_category": "prescription",
        "handling_flags": [],
        "special_instructions": "TEST_QA UI seed",
        "requested_pickup_time": "2026-07-20T15:00:00Z",
        "recipient_sms_consent": consent,
    }
    r = requests.post(f"{API}/facility/requests", headers=H(tokens["facility"]), json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def accept_pickup(jid):
    requests.post(f"{API}/jobs/{jid}/accept", headers=H(tokens["driver"]), timeout=30).raise_for_status()
    requests.post(f"{API}/jobs/{jid}/custody-events", headers=H(tokens["driver"]), timeout=30,
                  json={"event_type": "pickup_confirmed",
                        "checklist": {"label_confirmed": True, "item_count_confirmed": True}}).raise_for_status()


# (a) delivered job -> confirm token
job_a = book(True, "confirm")
accept_pickup(job_a["id"])
png = b"\x89PNG\r\n\x1a\n" + b"0" * 200
ev = requests.post(f"{API}/jobs/{job_a['id']}/delivery-evidence", headers=H(tokens["driver"]),
                   files={"file": ("sig.png", io.BytesIO(png), "image/png")},
                   data={"kind": "signature"}, timeout=60)
ev.raise_for_status()
requests.post(f"{API}/jobs/{job_a['id']}/custody-events", headers=H(tokens["driver"]), timeout=60,
              json={"event_type": "delivered", "evidence_url": ev.json()["evidence_url"],
                    "recipient_name": "TEST_QA UI"}).raise_for_status()
ob = requests.get(f"{API}/admin/sms-outbox?limit=200", headers=H(tokens["admin"]), timeout=30).json()
delivered = [m for m in ob["messages"] if m["job_id"] == job_a["id"] and m["kind"] == "delivered"]
token = delivered[0]["body"].split("/confirm/")[1].split()[0].rstrip(".")

# (b) picked_up job for driver1
job_b = book(True, "arriving")
accept_pickup(job_b["id"])

print("CONFIRM_TOKEN=", token)
print("DELIVERED_JOB=", job_a["id"])
print("ACTIVE_JOB=", job_b["id"])
