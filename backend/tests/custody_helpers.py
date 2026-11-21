"""Shared helpers for the NEW security model: drivers complete jobs only via the custody flow
(pickup_confirmed -> delivery-evidence -> delivered); file/CSV/PDF links need short-lived download tokens."""
import base64
import io

import requests

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")


def pickup(api, job_id, headers, cold=False):
    cl = {"label_confirmed": True, "item_count_confirmed": True}
    if cold:
        cl["cooler_confirmed"] = True
    return requests.post(f"{api}/jobs/{job_id}/custody-events", headers=headers, timeout=60,
                         json={"event_type": "pickup_confirmed", "checklist": cl})


def upload_evidence(api, job_id, headers, kind="signature"):
    headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}  # multipart sets its own
    r = requests.post(f"{api}/jobs/{job_id}/delivery-evidence", headers=headers, timeout=60,
                      files={"file": ("sig.png", io.BytesIO(PNG), "image/png")}, data={"kind": kind})
    assert r.status_code == 201, f"evidence upload {r.status_code} {r.text[:300]}"
    return r.json()["evidence_url"]


def deliver(api, job_id, headers, recipient="TEST_Recipient"):
    ev = upload_evidence(api, job_id, headers)
    return requests.post(f"{api}/jobs/{job_id}/custody-events", headers=headers, timeout=60,
                         json={"event_type": "delivered", "recipient_name": recipient, "evidence_url": ev})


def complete_via_custody(api, job_id, headers, cold=False, recipient="TEST_Recipient"):
    """Pickup (if not already picked up) + evidence + delivered. Returns the delivered response."""
    st = requests.get(f"{api}/jobs/{job_id}", headers=headers, timeout=60)
    status = st.json().get("status") if st.status_code == 200 else None
    if status not in ("picked_up", "in_transit"):
        p = pickup(api, job_id, headers, cold=cold)
        assert p.status_code == 201, f"pickup {p.status_code} {p.text[:300]}"
    return deliver(api, job_id, headers, recipient=recipient)


def download_token(api, headers):
    r = requests.get(f"{api}/auth/download-token", headers=headers, timeout=30)
    assert r.status_code == 200, f"download-token {r.status_code} {r.text[:200]}"
    return r.json()["token"]
