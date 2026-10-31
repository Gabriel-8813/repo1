import requests, concurrent.futures as cf
from dotenv import dotenv_values
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
def login(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["access_token"]}
F = login("demo.facility@meditrans.ca", "DemoFacility#2026")
D1 = login("driver1@test.com", "Driver@123")
D2 = login("demo.driver@meditrans.ca", "DemoDriver#2026")
A = login("demo.admin@meditrans.ca", "DemoAdmin#2026")
made = []
def book(city, flags=None):
    r = requests.post(f"{API}/facility/requests", headers=F, json={
        "recipient_name": "TEST_Probe", "recipient_phone": "+14165550100",
        "dropoff_address": f"1 Main St, {city}, ON", "item_count": 1, "item_category": "prescription",
        "handling_flags": flags or [], "requested_pickup_time": "2026-02-01T10:00", "consent_data_handling": True})
    j = r.json(); made.append(j["id"]); return j
try:
    # 1. bonus abuse: unrelated cities
    a, b = book("Ottawa"), book("Sudbury")
    r = requests.post(f"{API}/jobs/routes/accept", headers=D1, json={"job_ids": [a["id"], b["id"]]})
    print("1 cross-city bundle accept:", r.status_code, [x.get("payout_amount") for x in r.json().get("accepted", [])], "orig", a["payout_amount"], b["payout_amount"])
    # 2. cold-chain bypass by driver1
    c, d = book("Ottawa", ["cold_chain"]), book("Ottawa")
    av = requests.get(f"{API}/jobs/available", headers=D1).json()["jobs"]
    print("2 cold job visible to driver1 in /jobs/available:", any(x["id"] == c["id"] for x in av))
    r = requests.post(f"{API}/jobs/routes/accept", headers=D1, json={"job_ids": [c["id"], d["id"]]})
    print("2 cold-chain via route accept by driver1:", r.status_code, r.text[:150])
    # 3. race: two drivers concurrently
    e, f = book("Barrie"), book("Barrie")
    def acc(h): return requests.post(f"{API}/jobs/routes/accept", headers=h, json={"job_ids": [e["id"], f["id"]]}).status_code
    with cf.ThreadPoolExecutor(2) as ex:
        res = list(ex.map(acc, [D1, D2]))
    print("3 concurrent accept statuses:", res)
    j = requests.get(f"{API}/admin/jobs", headers=A)
    # 4. duplicate seal checks
    g = book("Guelph")
    requests.post(f"{API}/jobs/{g['id']}/accept", headers=D2)
    s = [requests.post(f"{API}/jobs/{g['id']}/verify-seal", headers=D2, json={"stage": "pickup", "intact": True}).status_code for _ in range(3)]
    s.append(requests.post(f"{API}/jobs/{g['id']}/verify-seal", headers=D2, json={"stage": "pickup", "intact": False}).status_code)
    v = requests.get(f"{API}/public/verify/{g['seal_code']}").json()
    print("4 repeated seal checks:", s, "public seal_checks:", [(x["stage"], x["intact"]) for x in v["seal_checks"]])
    # 5. pickup without seal check allowed?
    h = book("Guelph")
    requests.post(f"{API}/jobs/{h['id']}/accept", headers=D2)
    r = requests.post(f"{API}/jobs/{h['id']}/custody-events", headers=D2, json={"event_type": "pickup_confirmed", "checklist": {"label_confirmed": True, "item_count_confirmed": True}})
    print("5 pickup without seal check:", r.status_code)
finally:
    for jid in made:
        requests.delete(f"{API}/jobs/{jid}", headers=A)
    print("cleaned", len(made))
