"""Idempotent seed for app-store reviewer demo accounts (one per role)."""
import asyncio, os, sys, uuid
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

def hp(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

NOW = datetime.now(timezone.utc).isoformat()
PRIVACY = {"version": "1.0", "accepted_at": NOW}

ACCOUNTS = [
    ("demo.driver@meditrans.ca", "DemoDriver#2026", "Demo Driver", "driver"),
    ("demo.facility@meditrans.ca", "DemoFacility#2026", "Demo Facility Manager", "facility"),
    ("demo.dispatcher@meditrans.ca", "DemoDispatch#2026", "Demo Dispatcher", "dispatcher"),
    ("demo.admin@meditrans.ca", "DemoAdmin#2026", "Demo Admin", "admin"),
]

async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ids = {}
    for email, pw, name, role in ACCOUNTS:
        u = await db.users.find_one({"email": email})
        if u:
            await db.users.update_one({"email": email}, {"$set": {
                "password_hash": hp(pw), "role": role, "status": "approved", "privacy_policy": PRIVACY}})
            ids[role] = u["id"]
        else:
            uid = str(uuid.uuid4())
            await db.users.insert_one({
                "id": uid, "email": email, "password_hash": hp(pw), "full_name": name,
                "phone": "+14165550100", "role": role, "status": "approved",
                "created_at": NOW, "privacy_policy": PRIVACY, "driver_profile": None})
            ids[role] = uid
        print("seeded", role, email)

    future_expiry = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
    driver_rec = {
        "user_id": ids["driver"], "verification_status": "approved",
        "vehicle_type": "car", "vehicle_plate": "DEMO 001",
        "cvor_status": "valid", "tdg_cert_status": "valid",
        "vulnerable_sector_check_status": "valid", "insurance_status": "valid",
        "insurance_expiry": future_expiry, "cold_chain_certified": True,
        "total_trips": 0, "rating_avg": 0.0
    }
    existing = await db.drivers.find_one({"user_id": ids["driver"]})
    if existing:
        await db.drivers.update_one({"user_id": ids["driver"]}, {"$set": driver_rec})
    else:
        await db.drivers.insert_one({"id": str(uuid.uuid4()), **driver_rec, "created_at": NOW})
    print("driver record approved, insurance valid until", future_expiry)

    fac = await db.facilities.find_one({"owner_user_id": ids["facility"]})
    fac_doc = {
        "name": "Demo Medical Clinic", "type": "clinic",
        "address": "100 Queen St W, Toronto, ON",
        "contact_name": "Demo Facility Manager", "contact_phone": "+14165550101",
        "billing_email": "demo.facility@meditrans.ca", "status": "approved",
        "owner_user_id": ids["facility"]
    }
    if fac:
        await db.facilities.update_one({"owner_user_id": ids["facility"]}, {"$set": fac_doc})
    else:
        await db.facilities.insert_one({"id": str(uuid.uuid4()), **fac_doc, "created_at": NOW})
    print("facility record approved: Demo Medical Clinic")

asyncio.run(main())
