import requests
from dotenv import dotenv_values
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
def login(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["access_token"]}
F = login("demo.facility@meditrans.ca", "DemoFacility#2026")
D1 = login("driver1@test.com", "Driver@123")
A = login("demo.admin@meditrans.ca", "DemoAdmin#2026")
made = []
def book(city):
    r = requests.post(f"{API}/facility/requests", headers=F, json={
        "recipient_name": "TEST_Probe", "recipient_phone": "+14165550100",
        "dropoff_address": f"1 Main St, {city}, ON", "item_count": 1, "item_category": "prescription",
        "handling_flags": [], "requested_pickup_time": "2026-02-01T10:00", "consent_data_handling": True})
    j = r.json(); made.append(j["id"]); return j
try:
    a, b = book("Brampton"), book("Brampton")
    ids = [a["id"], b["id"]]
    print("orig", a["payout_amount"], b["payout_amount"])
    for rnd in range(3):
        r = requests.post(f"{API}/jobs/routes/accept", headers=D1, json={"job_ids": ids})
        print(f"round{rnd} accept", r.status_code, [x["payout_amount"] for x in r.json().get("accepted", [])])
        for i in ids:
            c = requests.post(f"{API}/jobs/{i}/cancel", headers=D1)
            print("  cancel", c.status_code, c.json().get("charged") if c.ok else c.text[:100])
    fd = requests.get(f"{API}/facility/deliveries", headers=F).json()
    lst = fd.get("deliveries") or fd.get("jobs") or fd
    print("facility sees payout:", [(x["payout_amount"], x.get("route_bundle")) for x in lst if x["id"] in ids])
finally:
    for jid in made:
        print("del", requests.delete(f"{API}/jobs/{jid}", headers=A).status_code)
