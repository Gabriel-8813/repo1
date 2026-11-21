import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
cli = AsyncIOMotorClient(env["MONGO_URL"])
db = cli[env["DB_NAME"]]

async def main():
    disp = await db.users.find_one({"email": "dispatcher1@test.com"}, {"_id": 0, "id": 1})
    fac_owned = await db.facilities.find({"owner_user_id": disp["id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(10)
    print("dispatcher owns facilities:", fac_owned)
    types = {}
    async for n in db.notifications.find({"user_id": disp["id"]}, {"_id": 0}):
        types[n.get("type")] = types.get(n.get("type"), 0) + 1
    print("dispatcher notif types:", types)
    # sample 'Delivery cancelled'
    n = await db.notifications.find_one({"user_id": disp["id"], "title": "Delivery cancelled"}, {"_id": 0})
    print("sample:", n)
    if n:
        j = await db.jobs.find_one({"id": n.get("job_id")}, {"_id": 0, "posted_by": 1, "facility_id": 1, "title": 1})
        print("job:", j)
    print("blank-title notifications total:", await db.notifications.count_documents({"title": {"$exists": False}}))
    print("leftover TEST_ jobs:", await db.jobs.count_documents({"title": {"$regex": "TEST_"}}),
          [j["title"] async for j in db.jobs.find({"title": {"$regex": "TEST_"}}, {"_id": 0, "title": 1})])
    print("TEST_QA recipient jobs:", [ (j["id"], j.get("title"), j.get("status")) async for j in db.jobs.find({"recipient_name": {"$regex": "TEST_QA"}}, {"_id": 0, "id":1,"title": 1, "status": 1})])

asyncio.run(main())
