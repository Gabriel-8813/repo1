"""One-time migration: encrypt existing PII + backfill audit hash chain."""
import asyncio, os, sys, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

fernet = Fernet(os.environ["DATA_ENCRYPTION_KEY"].encode())
ENC = "enc::"

def enc(v):
    if not v or not isinstance(v, str) or v.startswith(ENC) or v == "[REDACTED]":
        return v
    return ENC + fernet.encrypt(v.encode()).decode()

def audit_hash(e):
    material = json.dumps({
        "seq": e["seq"], "actor_id": e["actor_id"], "actor_role": e.get("actor_role"),
        "action": e["action"], "entity": e["entity"], "entity_id": e["entity_id"],
        "timestamp": e["timestamp"], "details": e.get("details"), "prev_hash": e["prev_hash"]
    }, sort_keys=True, default=str)
    return hashlib.sha256(material.encode()).hexdigest()

async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    n = 0
    async for j in db.jobs.find({}, {"_id": 1, "recipient_name": 1, "recipient_phone": 1}):
        upd = {}
        for f in ("recipient_name", "recipient_phone"):
            e = enc(j.get(f))
            if e != j.get(f):
                upd[f] = e
        if upd:
            await db.jobs.update_one({"_id": j["_id"]}, {"$set": upd})
            n += 1
    m = 0
    async for ev in db.custody_events.find({}, {"_id": 1, "recipient_name": 1, "recipient_relationship": 1}):
        upd = {}
        for f in ("recipient_name", "recipient_relationship"):
            e = enc(ev.get(f))
            if e != ev.get(f):
                upd[f] = e
        if upd:
            await db.custody_events.update_one({"_id": ev["_id"]}, {"$set": upd})
            m += 1
    print(f"encrypted PII: {n} jobs, {m} custody events")

    entries = await db.audit_logs.find({"seq": {"$exists": False}}, {"_id": 1, "id": 1, "actor_id": 1, "actor_role": 1, "action": 1, "entity": 1, "entity_id": 1, "timestamp": 1, "details": 1}).sort("timestamp", 1).to_list(100000)
    last = await db.audit_logs.find_one({"seq": {"$exists": True}}, {"_id": 0, "seq": 1, "hash": 1}, sort=[("seq", -1)])
    seq = (last["seq"] + 1) if last else 1
    prev_hash = last["hash"] if last else "genesis"
    for e in entries:
        e["seq"] = seq
        e["prev_hash"] = prev_hash
        h = audit_hash(e)
        await db.audit_logs.update_one({"_id": e["_id"]}, {"$set": {"seq": seq, "prev_hash": prev_hash, "hash": h}})
        prev_hash = h
        seq += 1
    print(f"hash-chained audit entries: {len(entries)} (chain now ends at seq {seq - 1})")

asyncio.run(main())
