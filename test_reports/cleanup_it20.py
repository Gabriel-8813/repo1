"""Cleanup of TEST_ data created during iteration 20 testing."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
db = AsyncIOMotorClient(env["MONGO_URL"])[env["DB_NAME"]]


async def main():
    q = {"$or": [{"recipient_name": {"$regex": "^TEST_"}}, {"title": {"$regex": "^TEST_"}}]}
    ids = [j["id"] async for j in db.jobs.find(q, {"_id": 0, "id": 1})]
    print("jobs to delete:", len(ids))
    r = await db.jobs.delete_many({"id": {"$in": ids}})
    print("jobs deleted:", r.deleted_count)
    for coll in ("notifications", "custody_events", "sms_outbox", "delivery_evidence", "reviews", "earnings", "ledger"):
        d = await db[coll].delete_many({"job_id": {"$in": ids}})
        print(coll, "deleted:", d.deleted_count)
    # legacy notifications for jobs that no longer exist
    live = {j["id"] async for j in db.jobs.find({}, {"_id": 0, "id": 1})}
    orphan = [n["id"] async for n in db.notifications.find({}, {"_id": 0, "id": 1, "job_id": 1}) if n.get("job_id") and n["job_id"] not in live]
    d = await db.notifications.delete_many({"id": {"$in": orphan}})
    print("orphan notifications deleted:", d.deleted_count)
    await db.sms_optouts.delete_many({"phone": {"$in": ["+14165559999", "+14165550123", "+14165557788"]}})
    print("remaining optouts:", await db.sms_optouts.count_documents({}))
    print("driver1 active jobs:", await db.jobs.count_documents({"accepted_by": {"$ne": None}, "status": {"$in": ["accepted", "picked_up", "in_transit"]}}))
    print("total jobs left:", await db.jobs.count_documents({}))

asyncio.run(main())
