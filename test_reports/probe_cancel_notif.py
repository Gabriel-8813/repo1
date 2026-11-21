import asyncio, sys, requests
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values
from tests.test_notifications_sms import API, H, _login

env = dotenv_values("/app/backend/.env")
cli = AsyncIOMotorClient(env["MONGO_URL"])
db = cli[env["DB_NAME"]]

tokens = {r: _login(r) for r in ("admin", "dispatcher", "facility")}

payload = {
    "recipient_name": "TEST_QA probe cancel", "dropoff_address": "300 Front St W, Toronto, ON",
    "recipient_phone": "+14165559999", "item_count": 1, "item_category": "prescription",
    "handling_flags": [], "requested_pickup_time": "2026-07-20T15:00:00Z", "recipient_sms_consent": False,
}
job = requests.post(f"{API}/facility/requests", headers=H(tokens["facility"]), json=payload, timeout=60).json()
print("posted_by == facility?", job["posted_by"])
r = requests.put(f"{API}/jobs/{job['id']}", headers=H(tokens["dispatcher"]), json={"status": "cancelled"}, timeout=30)
print("cancel:", r.status_code)

async def main():
    users = {u["id"]: (u["email"], u["role"]) async for u in db.users.find({}, {"_id": 0, "id": 1, "email": 1, "role": 1})}
    async for n in db.notifications.find({"job_id": job["id"]}, {"_id": 0}):
        print(users.get(n["user_id"]), "|", n.get("type"), "|", n.get("title"), "|", n.get("body") or n.get("message"))
    print("facility owner of job facility:", await db.facilities.find_one({"id": job["facility_id"]}, {"_id": 0, "owner_user_id": 1, "name": 1}))
    await db.jobs.delete_one({"id": job["id"]})
    await db.notifications.delete_many({"job_id": job["id"]})

asyncio.run(main())
