"""Iteration 24 cleanup + driver-document download-token probe."""
import requests
from dotenv import dotenv_values
from pymongo import MongoClient
e = dotenv_values("/app/backend/.env")
db = MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"] + "/api"

# driver-doc probe
doc = db.driver_documents.find_one({}, {"_id": 0, "id": 1})
if doc:
    t = requests.post(f"{API}/auth/login", json={"email": "demo.admin@meditrans.ca", "password": "DemoAdmin#2026"}).json()["access_token"]
    dl = requests.get(f"{API}/auth/download-token", headers={"Authorization": f"Bearer {t}"}).json()["token"]
    print("driver doc dl-token:", requests.get(f"{API}/driver-documents/{doc['id']}/file?auth={dl}").status_code,
          "session-in-query:", requests.get(f"{API}/driver-documents/{doc['id']}/file?auth={t}").status_code)
else:
    print("no driver documents in DB")

# review created via UI on my own job
print("reviews deleted:", db.reviews.delete_many({"job_id": "aa0d1e17-dcaa-46df-924d-dbf984ad1f3c"}).deleted_count)
print("leftover TEST users:", db.users.count_documents({"email": {"$regex": "^test_hard_"}}))
print("leftover TEST facilities:", db.facilities.count_documents({"name": "TEST_Pending Clinic"}))
print("open TEST jobs:", db.jobs.count_documents({"status": "open", "recipient_name": {"$regex": "TEST_"}}))
