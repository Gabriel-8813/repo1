import requests
from dotenv import dotenv_values
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
A = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "demo.admin@meditrans.ca", "password": "DemoAdmin#2026"}).json()["access_token"]}
for jid in ["0f1e9a5d-b994-4ee0-a2ef-eb7fe9d3b123", "6c96d00a-d499-4b6f-b4cc-a04b6d8ead61", "de836347-0fc3-4a83-a955-0e09fd99104f"]:
    print(jid, requests.delete(f"{API}/jobs/{jid}", headers=A).status_code)
