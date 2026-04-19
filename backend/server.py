from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'meditrans_secret_key')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Stripe Config
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')

# Admin Config
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').lower().strip()

# Default Fee Agreement (commission-based revenue model)
DEFAULT_FEE_AGREEMENT = {
    "base_rate_per_km": 1.50,
    "minimum_fee": 25.00,
    "urgent_multiplier": 1.5,
    "emergency_multiplier": 2.0,
    "temperature_controlled_fee": 15.00,
    "commission_rate": 0.20,               # 20% platform commission on completed trips
    "cancellation_fee": 15.00,             # charged if driver cancels after grace window
    "cancellation_grace_minutes": 5,       # minutes after accept during which cancel is free
    "currency": "CAD"
}

async def get_fees_from_db() -> dict:
    doc = await db.settings.find_one({"key": "fee_agreement"}, {"_id": 0})
    if doc and doc.get("value"):
        # Merge with defaults to keep forward-compat
        return {**DEFAULT_FEE_AGREEMENT, **doc["value"]}
    return DEFAULT_FEE_AGREEMENT

# Ontario Permit Requirements
ONTARIO_PERMITS = [
    {
        "id": "cvor",
        "name": "Commercial Vehicle Operator's Registration (CVOR)",
        "description": "Required for operating commercial motor vehicles in Ontario",
        "issuing_authority": "Ontario Ministry of Transportation",
        "url": "https://www.ontario.ca/page/commercial-vehicle-operators-registration-cvor",
        "required": True
    },
    {
        "id": "tdg",
        "name": "Transportation of Dangerous Goods (TDG) Certificate",
        "description": "Required for transporting biological and medical materials classified as dangerous goods",
        "issuing_authority": "Transport Canada",
        "url": "https://tc.canada.ca/en/dangerous-goods/transportation-dangerous-goods-training",
        "required": True
    },
    {
        "id": "driver_license",
        "name": "Ontario Driver's License (Class G or higher)",
        "description": "Valid Ontario driver's license appropriate for vehicle class",
        "issuing_authority": "ServiceOntario",
        "url": "https://www.ontario.ca/page/get-g-drivers-licence-new-drivers",
        "required": True
    },
    {
        "id": "vulnerable_sector",
        "name": "Vulnerable Sector Check",
        "description": "Criminal background check required for handling sensitive medical deliveries",
        "issuing_authority": "Local Police Service",
        "url": "https://www.ontario.ca/page/police-record-checks",
        "required": True
    },
    {
        "id": "vehicle_insurance",
        "name": "Commercial Vehicle Insurance",
        "description": "Minimum $2M liability coverage for commercial medical transport",
        "issuing_authority": "Licensed Insurance Provider",
        "url": "https://www.fsrao.ca/consumers/auto-insurance",
        "required": True
    },
    {
        "id": "first_aid",
        "name": "First Aid & CPR Certification",
        "description": "Standard first aid with CPR level C certification",
        "issuing_authority": "Red Cross or St. John Ambulance",
        "url": "https://www.redcross.ca/training-and-certification/course-descriptions/first-aid-at-home-background-information/standard-first-aid",
        "required": False
    }
]

# Create the main app
app = FastAPI(title="MediTrans Ontario API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Pydantic Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str
    role: str
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class DriverProfile(BaseModel):
    vehicle_type: str
    vehicle_year: int
    vehicle_make: str
    vehicle_model: str
    license_plate: str
    permits: Dict[str, bool] = {}

class DriverProfileUpdate(BaseModel):
    vehicle_type: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    license_plate: Optional[str] = None
    permits: Optional[Dict[str, bool]] = None

class JobCreate(BaseModel):
    title: str
    pickup_address: str
    delivery_address: str
    pickup_city: str
    delivery_city: str
    goods_type: str
    temperature_controlled: bool = False
    urgency: str = "standard"  # standard, urgent, emergency
    estimated_distance_km: float
    offered_price: float
    notes: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    title: str
    pickup_address: str
    delivery_address: str
    pickup_city: str
    delivery_city: str
    goods_type: str
    temperature_controlled: bool
    urgency: str
    estimated_distance_km: float
    offered_price: float
    notes: Optional[str]
    status: str
    posted_by: str
    accepted_by: Optional[str]
    created_at: str
    accepted_at: Optional[str]
    completed_at: Optional[str]

class FeeAgreement(BaseModel):
    base_rate_per_km: float = 1.50
    minimum_fee: float = 25.00
    urgent_multiplier: float = 1.5
    emergency_multiplier: float = 2.0
    temperature_controlled_fee: float = 15.00
    commission_rate: float = 0.20
    cancellation_fee: float = 15.00
    cancellation_grace_minutes: int = 5

class CheckoutRequest(BaseModel):
    origin_url: str

class PaymentTransaction(BaseModel):
    id: str
    user_id: str
    session_id: str
    plan_id: str
    amount: float
    currency: str
    status: str
    payment_status: str
    created_at: str
    updated_at: str

# Admin Models
class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None  # "admin" or "driver"

class FeeAgreementUpdate(BaseModel):
    base_rate_per_km: Optional[float] = None
    minimum_fee: Optional[float] = None
    urgent_multiplier: Optional[float] = None
    emergency_multiplier: Optional[float] = None
    temperature_controlled_fee: Optional[float] = None
    commission_rate: Optional[float] = None
    cancellation_fee: Optional[float] = None
    cancellation_grace_minutes: Optional[int] = None

class JobAdminUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    offered_price: Optional[float] = None
    urgency: Optional[str] = None
    notes: Optional[str] = None

# Auth helpers
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Auth Routes
@api_router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    # Auto-promote creator admin based on ADMIN_EMAIL env
    role = "admin" if ADMIN_EMAIL and user_data.email.lower().strip() == ADMIN_EMAIL else "driver"
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "phone": user_data.phone,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "driver_profile": None
    }
    
    await db.users.insert_one(user_doc)
    
    token = create_token(user_id, user_data.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=user_data.email,
            full_name=user_data.full_name,
            phone=user_data.phone,
            role=role,
            created_at=user_doc["created_at"]
        )
    )

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Lazy auto-promote if ADMIN_EMAIL matches and user isn't admin yet
    if ADMIN_EMAIL and user["email"].lower().strip() == ADMIN_EMAIL and user.get("role") != "admin":
        await db.users.update_one({"id": user["id"]}, {"$set": {"role": "admin"}})
        user["role"] = "admin"
    token = create_token(user["id"], user["email"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            phone=user["phone"],
            role=user["role"],
            created_at=user["created_at"]
        )
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        phone=current_user["phone"],
        role=current_user["role"],
        created_at=current_user["created_at"]
    )

# Driver Profile Routes
@api_router.get("/driver/profile")
async def get_driver_profile(current_user: dict = Depends(get_current_user)):
    return {"profile": current_user.get("driver_profile")}

@api_router.put("/driver/profile")
async def update_driver_profile(profile: DriverProfileUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in profile.model_dump().items() if v is not None}
    if update_data:
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {"driver_profile": {**current_user.get("driver_profile", {}), **update_data}}}
        )
    updated_user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    return {"profile": updated_user.get("driver_profile")}

# Permit Routes
@api_router.get("/permits")
async def get_permits():
    return {"permits": ONTARIO_PERMITS}

@api_router.get("/driver/permits")
async def get_driver_permits(current_user: dict = Depends(get_current_user)):
    profile = current_user.get("driver_profile") or {}
    permits = profile.get("permits", {})
    return {"permits": permits}

@api_router.put("/driver/permits/{permit_id}")
async def update_driver_permit(permit_id: str, completed: bool, current_user: dict = Depends(get_current_user)):
    profile = current_user.get("driver_profile") or {}
    permits = profile.get("permits", {})
    permits[permit_id] = completed
    
    # Initialize driver_profile if it's null
    if current_user.get("driver_profile") is None:
        profile = {"permits": permits}
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {"driver_profile": profile}}
        )
    else:
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {"driver_profile.permits": permits}}
        )
    return {"permit_id": permit_id, "completed": completed}

# ======================
# Commission / Balance / Payment Routes
# ======================
@api_router.get("/driver/balance")
async def get_driver_balance(current_user: dict = Depends(get_current_user)):
    entries = await db.ledger.find(
        {"driver_id": current_user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    owed = sum(e.get("amount", 0) for e in entries if e.get("status") == "owed")
    paid = sum(e.get("amount", 0) for e in entries if e.get("status") == "paid")
    return {
        "owed": round(owed, 2),
        "paid": round(paid, 2),
        "currency": "CAD",
        "entries": entries
    }

@api_router.post("/payments/balance/checkout")
async def create_balance_checkout(checkout_req: CheckoutRequest, request: Request, current_user: dict = Depends(get_current_user)):
    # Calculate owed balance (server-side, never trust client)
    entries_cursor = db.ledger.find(
        {"driver_id": current_user["id"], "status": "owed"}, {"_id": 0}
    )
    owed_entries = await entries_cursor.to_list(1000)
    owed_total = round(sum(e.get("amount", 0) for e in owed_entries), 2)
    if owed_total <= 0:
        raise HTTPException(status_code=400, detail="No outstanding balance to pay")
    
    owed_ids = [e["id"] for e in owed_entries]
    
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    success_url = f"{checkout_req.origin_url}/billing?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{checkout_req.origin_url}/billing"
    
    checkout_request = CheckoutSessionRequest(
        amount=owed_total,
        currency="cad",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": current_user["id"],
            "payment_type": "balance",
            "ledger_ids": ",".join(owed_ids)
        }
    )
    
    session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
    
    transaction_doc = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "session_id": session.session_id,
        "payment_type": "balance",
        "ledger_ids": owed_ids,
        "amount": owed_total,
        "currency": "cad",
        "status": "pending",
        "payment_status": "initiated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.payment_transactions.insert_one(transaction_doc)
    
    return {"checkout_url": session.url, "session_id": session.session_id, "amount": owed_total}

async def _settle_ledger_for_session(session_id: str):
    """Mark ledger entries as paid once Stripe confirms payment."""
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx or tx.get("payment_status") != "paid":
        return
    ledger_ids = tx.get("ledger_ids") or []
    if ledger_ids:
        await db.ledger.update_many(
            {"id": {"$in": ledger_ids}, "status": "owed"},
            {"$set": {
                "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "payment_session_id": session_id
            }}
        )

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    try:
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        
        if tx and tx.get("payment_status") != "paid" and status.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "status": status.status,
                    "payment_status": status.payment_status,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            await _settle_ledger_for_session(session_id)
        
        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    try:
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        if webhook_response.payment_status == "paid":
            tx = await db.payment_transactions.find_one(
                {"session_id": webhook_response.session_id}, {"_id": 0}
            )
            if tx and tx.get("payment_status") != "paid":
                await db.payment_transactions.update_one(
                    {"session_id": webhook_response.session_id},
                    {"$set": {
                        "status": "complete",
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                await _settle_ledger_for_session(webhook_response.session_id)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

@api_router.get("/payments/history")
async def get_payment_history(current_user: dict = Depends(get_current_user)):
    transactions = await db.payment_transactions.find(
        {"user_id": current_user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"transactions": transactions}

# Job Routes
@api_router.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate, current_user: dict = Depends(get_current_user)):
    job_id = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        **job.model_dump(),
        "status": "open",
        "posted_by": current_user["id"],
        "accepted_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "accepted_at": None,
        "completed_at": None
    }
    await db.jobs.insert_one(job_doc)
    return JobResponse(**job_doc)

@api_router.get("/jobs")
async def get_jobs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if status:
        query["status"] = status
    
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"jobs": jobs}

@api_router.get("/jobs/available")
async def get_available_jobs(current_user: dict = Depends(get_current_user)):
    jobs = await db.jobs.find({"status": "open"}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"jobs": jobs}

@api_router.get("/jobs/my")
async def get_my_jobs(current_user: dict = Depends(get_current_user)):
    jobs = await db.jobs.find(
        {"$or": [{"posted_by": current_user["id"]}, {"accepted_by": current_user["id"]}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"jobs": jobs}

@api_router.post("/jobs/{job_id}/accept")
async def accept_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "open":
        raise HTTPException(status_code=400, detail="Job is no longer available")
    
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "in_progress",
            "accepted_by": current_user["id"],
            "accepted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": updated_job}

@api_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Driver cancels a job they previously accepted.
    Within the grace window (default 5 min) it's free; after that a cancellation fee is charged."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Only in-progress jobs can be cancelled")
    if job.get("accepted_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the assigned driver can cancel this job")
    
    fees = await get_fees_from_db()
    grace_min = fees.get("cancellation_grace_minutes", 5)
    fee_amount = fees.get("cancellation_fee", 15.00)
    
    accepted_at = datetime.fromisoformat(job["accepted_at"])
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - accepted_at).total_seconds()
    charged = elapsed_seconds > (grace_min * 60)
    
    # Reopen the job so other drivers can accept it
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "open",
            "accepted_by": None,
            "accepted_at": None,
            "last_cancelled_by": current_user["id"],
            "last_cancelled_at": now.isoformat()
        }}
    )
    
    ledger_entry = None
    if charged:
        ledger_entry = {
            "id": str(uuid.uuid4()),
            "driver_id": current_user["id"],
            "job_id": job_id,
            "type": "cancellation_fee",
            "amount": round(fee_amount, 2),
            "status": "owed",
            "currency": "CAD",
            "description": f"Late cancellation fee (after {grace_min} min grace window)",
            "created_at": now.isoformat()
        }
        await db.ledger.insert_one(ledger_entry)
        ledger_entry.pop("_id", None)
    
    return {
        "job_id": job_id,
        "charged": charged,
        "grace_minutes": grace_min,
        "elapsed_seconds": int(elapsed_seconds),
        "cancellation_fee": round(fee_amount, 2) if charged else 0.0,
        "ledger_entry": ledger_entry
    }

@api_router.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["accepted_by"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the assigned driver can complete this job")
    if job.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Only in-progress jobs can be completed")
    
    now = datetime.now(timezone.utc)
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "completed",
            "completed_at": now.isoformat()
        }}
    )
    
    # Record gross earnings (what the driver charged the customer)
    gross = float(job["offered_price"])
    earnings_doc = {
        "id": str(uuid.uuid4()),
        "driver_id": current_user["id"],
        "job_id": job_id,
        "amount": gross,
        "created_at": now.isoformat()
    }
    await db.earnings.insert_one(earnings_doc)
    
    # Record platform commission as owed ledger entry
    fees = await get_fees_from_db()
    commission_rate = float(fees.get("commission_rate", 0.20))
    commission_amount = round(gross * commission_rate, 2)
    ledger_entry = {
        "id": str(uuid.uuid4()),
        "driver_id": current_user["id"],
        "job_id": job_id,
        "type": "commission",
        "amount": commission_amount,
        "status": "owed",
        "currency": "CAD",
        "description": f"{int(commission_rate * 100)}% platform commission on trip ${gross:.2f}",
        "created_at": now.isoformat()
    }
    await db.ledger.insert_one(ledger_entry)
    ledger_entry.pop("_id", None)
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {
        "job": updated_job,
        "gross_earnings": gross,
        "commission_charged": commission_amount,
        "net_earnings": round(gross - commission_amount, 2)
    }

# Fee Agreement Routes
@api_router.get("/fees/agreement")
async def get_fee_agreement():
    fees = await get_fees_from_db()
    return {"agreement": fees}

# Earnings Routes
@api_router.get("/earnings")
async def get_earnings(current_user: dict = Depends(get_current_user)):
    earnings = await db.earnings.find({"driver_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    total = sum(e.get("amount", 0) for e in earnings)
    return {"earnings": earnings, "total": total}

@api_router.get("/earnings/stats")
async def get_earnings_stats(current_user: dict = Depends(get_current_user)):
    earnings = await db.earnings.find({"driver_id": current_user["id"]}, {"_id": 0}).to_list(1000)
    
    total = sum(e.get("amount", 0) for e in earnings)
    jobs_completed = len(earnings)
    
    # This month's earnings
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = sum(
        e.get("amount", 0) for e in earnings 
        if datetime.fromisoformat(e["created_at"]) >= month_start
    )
    
    return {
        "total_earnings": total,
        "jobs_completed": jobs_completed,
        "this_month": this_month,
        "currency": "CAD"
    }

# ======================
# Admin Routes (RBAC)
# ======================
@api_router.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    total_users = await db.users.count_documents({})
    admin_count = await db.users.count_documents({"role": "admin"})
    total_jobs = await db.jobs.count_documents({})
    open_jobs = await db.jobs.count_documents({"status": "open"})
    in_progress_jobs = await db.jobs.count_documents({"status": "in_progress"})
    completed_jobs = await db.jobs.count_documents({"status": "completed"})

    ledger_entries = await db.ledger.find({}, {"_id": 0}).to_list(100000)
    commission_owed = round(sum(e["amount"] for e in ledger_entries if e.get("type") == "commission" and e.get("status") == "owed"), 2)
    commission_paid = round(sum(e["amount"] for e in ledger_entries if e.get("type") == "commission" and e.get("status") == "paid"), 2)
    cancel_fee_owed = round(sum(e["amount"] for e in ledger_entries if e.get("type") == "cancellation_fee" and e.get("status") == "owed"), 2)
    cancel_fee_paid = round(sum(e["amount"] for e in ledger_entries if e.get("type") == "cancellation_fee" and e.get("status") == "paid"), 2)

    paid_tx_count = await db.payment_transactions.count_documents({"payment_status": "paid"})
    return {
        "total_users": total_users,
        "admin_count": admin_count,
        "total_jobs": total_jobs,
        "open_jobs": open_jobs,
        "in_progress_jobs": in_progress_jobs,
        "completed_jobs": completed_jobs,
        "commission_owed": commission_owed,
        "commission_paid": commission_paid,
        "cancellation_fees_owed": cancel_fee_owed,
        "cancellation_fees_paid": cancel_fee_paid,
        "total_revenue": round(commission_paid + cancel_fee_paid, 2),
        "total_outstanding": round(commission_owed + cancel_fee_owed, 2),
        "paid_transactions": paid_tx_count,
        "currency": "CAD"
    }

@api_router.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return {"users": users}

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, update: AdminUserUpdate, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    if data.get("role") and data["role"] not in ("admin", "driver"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if data:
        await db.users.update_one({"id": user_id}, {"$set": data})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"user": updated}

@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted", "user_id": user_id}

@api_router.get("/admin/jobs")
async def admin_list_jobs(admin: dict = Depends(require_admin)):
    jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"jobs": jobs}

@api_router.put("/admin/jobs/{job_id}")
async def admin_update_job(job_id: str, update: JobAdminUpdate, admin: dict = Depends(require_admin)):
    existing = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    if data.get("status") and data["status"] not in ("open", "in_progress", "completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if data:
        await db.jobs.update_one({"id": job_id}, {"$set": data})
    updated = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": updated}

@api_router.delete("/admin/jobs/{job_id}")
async def admin_delete_job(job_id: str, admin: dict = Depends(require_admin)):
    result = await db.jobs.delete_one({"id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}

@api_router.get("/admin/fees")
async def admin_get_fees(admin: dict = Depends(require_admin)):
    fees = await get_fees_from_db()
    return {"agreement": fees}

@api_router.put("/admin/fees")
async def admin_update_fees(update: FeeAgreementUpdate, admin: dict = Depends(require_admin)):
    fees = await get_fees_from_db()
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    fees = {**fees, **data}
    fees["currency"] = "CAD"
    await db.settings.update_one(
        {"key": "fee_agreement"},
        {"$set": {"value": fees, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"agreement": fees}

@api_router.get("/admin/ledger")
async def admin_list_ledger(admin: dict = Depends(require_admin)):
    entries = await db.ledger.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return {"entries": entries}

@api_router.get("/admin/transactions")
async def admin_list_transactions(admin: dict = Depends(require_admin)):
    tx = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"transactions": tx}

# Health check
@api_router.get("/")
async def root():
    return {"message": "MediTrans Ontario API", "status": "healthy"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    # Seed default fees if missing
    if not await db.settings.find_one({"key": "fee_agreement"}):
        await db.settings.insert_one({
            "key": "fee_agreement",
            "value": DEFAULT_FEE_AGREEMENT,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    # Clean up legacy subscription_plans settings doc (revenue model switched to commission)
    await db.settings.delete_one({"key": "subscription_plans"})
    # Remove stale subscription fields from users (cosmetic cleanup, harmless if absent)
    await db.users.update_many({}, {"$unset": {
        "subscription_plan": "", "subscription_status": "", "subscription_expires": ""
    }})
    # Auto-promote admin if ADMIN_EMAIL user already exists
    if ADMIN_EMAIL:
        await db.users.update_one(
            {"email": ADMIN_EMAIL},
            {"$set": {"role": "admin"}}
        )
        logger.info(f"Admin auto-promote ensured for: {ADMIN_EMAIL}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
