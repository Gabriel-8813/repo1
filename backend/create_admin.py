"""One-off CLI to create or promote an admin account.

Usage:
    python create_admin.py admin@example.com            # promote existing user
    python create_admin.py admin@example.com 'Pass#123' # create if missing (password >= 8 chars)
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    email = sys.argv[1].lower().strip()
    password = sys.argv[2] if len(sys.argv) > 2 else None
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1})
    if user:
        await db.users.update_one({"id": user["id"]}, {"$set": {"role": "admin"}, "$inc": {"token_version": 1}})
        print(f"Promoted existing user {email} to admin (sessions revoked, re-login required).")
        return
    if not password or len(password) < 8:
        print("User not found. To create one, pass a password of at least 8 characters.")
        sys.exit(1)
    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one({
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "full_name": "Administrator",
        "phone": None,
        "role": "admin",
        "status": "approved",
        "token_version": 0,
        "created_at": now,
        "privacy_policy": {"version": "1.0", "accepted_at": now},
        "driver_profile": None,
    })
    print(f"Created admin account {email}.")


if __name__ == "__main__":
    asyncio.run(main())
