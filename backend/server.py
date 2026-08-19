from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Query, Response
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
import stripe
import resend
import asyncio
import hashlib
import re
import requests
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
stripe.api_key = STRIPE_API_KEY

# Resend (email)
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev').strip()
RESET_LINK_BASE_URL = os.environ.get('RESET_LINK_BASE_URL', '').rstrip('/')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str
    role: str
    created_at: str
    verification_status: Optional[str] = None

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
    title: Optional[str] = "Medical Transport"
    pickup_address: str
    delivery_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    pickup_city: Optional[str] = ""
    delivery_city: Optional[str] = ""
    goods_type: Optional[str] = None
    temperature_controlled: bool = False
    urgency: str = "standard"  # standard, urgent, emergency
    estimated_distance_km: Optional[float] = None
    distance_km: Optional[float] = None
    offered_price: Optional[float] = None
    payout_amount: Optional[float] = None
    notes: Optional[str] = None
    facility_id: Optional[str] = None
    item_category: Optional[str] = None
    handling_flags: List[str] = []
    special_instructions: Optional[str] = None  # non-clinical handling notes only

class JobResponse(BaseModel):
    id: str
    title: Optional[str] = None
    pickup_address: str
    delivery_address: str
    pickup_city: Optional[str] = ""
    delivery_city: Optional[str] = ""
    goods_type: Optional[str] = None
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
    dropoff_address: Optional[str] = None
    distance_km: Optional[float] = None
    payout_amount: Optional[float] = None
    facility_id: Optional[str] = None
    item_category: Optional[str] = None
    handling_flags: List[str] = []
    special_instructions: Optional[str] = None
    assigned_driver_id: Optional[str] = None
    picked_up_at: Optional[str] = None
    delivered_at: Optional[str] = None

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

class PermitCreate(BaseModel):
    id: str
    name: str
    description: str
    issuing_authority: str
    url: str
    required: bool = True

class PermitUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    issuing_authority: Optional[str] = None
    url: Optional[str] = None
    required: Optional[bool] = None

class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    reviewer_name: Optional[str] = None

# ---- Marketplace shared data model (enums + models) ----
USER_ROLES = {"driver", "facility", "dispatcher", "admin"}
USER_STATUSES = {"pending", "approved", "suspended"}
FACILITY_TYPES = {"pharmacy", "clinic", "lab", "hospital", "health_shop", "other"}
ITEM_CATEGORIES = {"prescription", "lab_sample", "biological", "medical_equipment", "medical_supply", "other"}
HANDLING_FLAGS = {"cold_chain", "controlled_substance", "fragile", "urgent", "signature_required", "id_required"}
# "open"/"completed" kept as legacy aliases of "created"/"delivered"
JOB_STATUSES = {"created", "offered", "accepted", "picked_up", "in_transit", "delivered", "cancelled", "returned", "open", "completed", "in_progress"}
DRIVER_VERIFICATION_STATUSES = {"incomplete", "pending_review", "approved", "rejected", "suspended"}
COMPLIANCE_STATUSES = {"not_submitted", "pending", "valid", "expired", "rejected"}
CUSTODY_EVENT_TYPES = {"pickup_confirmed", "in_transit_ping", "delivery_attempted", "delivered", "returned", "exception"}

class MarketplaceUserCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str
    role: str = "driver"
    status: str = "pending"

class MarketplaceUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class DriverRecordCreate(BaseModel):
    user_id: Optional[str] = None  # admin may set; defaults to caller
    vehicle_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    cvor_status: str = "not_submitted"
    tdg_cert_status: str = "not_submitted"
    vulnerable_sector_check_status: str = "not_submitted"
    insurance_status: str = "not_submitted"
    insurance_expiry: Optional[str] = None
    cold_chain_certified: bool = False
    verification_status: str = "incomplete"

class DriverRecordUpdate(BaseModel):
    vehicle_type: Optional[str] = None
    vehicle_plate: Optional[str] = None
    cvor_status: Optional[str] = None
    tdg_cert_status: Optional[str] = None
    vulnerable_sector_check_status: Optional[str] = None
    insurance_status: Optional[str] = None
    insurance_expiry: Optional[str] = None
    cold_chain_certified: Optional[bool] = None
    verification_status: Optional[str] = None
    rating_avg: Optional[float] = None
    total_trips: Optional[int] = None

class FacilityCreate(BaseModel):
    name: str
    type: str
    address: str
    contact_name: str
    contact_phone: str
    billing_email: EmailStr
    status: str = "pending"

class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    status: Optional[str] = None
    per_delivery_rate: Optional[float] = Field(default=None, ge=0)
    commission_rate_override: Optional[float] = Field(default=None, ge=0, le=1)

class JobUpdate(BaseModel):
    title: Optional[str] = None
    pickup_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    item_category: Optional[str] = None
    handling_flags: Optional[List[str]] = None
    distance_km: Optional[float] = None
    payout_amount: Optional[float] = None
    special_instructions: Optional[str] = None
    status: Optional[str] = None
    assigned_driver_id: Optional[str] = None
    facility_id: Optional[str] = None
    urgency: Optional[str] = None
    notes: Optional[str] = None

def validate_enum(value, allowed: set, field: str):
    if value is not None and value not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid {field} '{value}'. Allowed: {sorted(allowed)}")

def validate_handling_flags(flags):
    if flags:
        bad = set(flags) - HANDLING_FLAGS
        if bad:
            raise HTTPException(status_code=422, detail=f"Invalid handling_flags {sorted(bad)}. Allowed: {sorted(HANDLING_FLAGS)}")

class CustodyEventCreate(BaseModel):
    event_type: str
    gps_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    gps_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    evidence_url: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_relationship: Optional[str] = None
    notes: Optional[str] = None
    checklist: Optional[dict] = None

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

# ---- RBAC helpers ----
STAFF_ROLES = {"admin", "dispatcher"}

async def require_staff(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Dispatcher or admin access required")
    return current_user

DRIVER_JOB_FIELDS = {
    "id", "title", "pickup_address", "delivery_address", "dropoff_address",
    "pickup_city", "delivery_city", "goods_type", "temperature_controlled",
    "urgency", "estimated_distance_km", "distance_km", "offered_price",
    "payout_amount", "notes", "special_instructions", "item_category",
    "handling_flags", "status", "created_at", "accepted_at", "picked_up_at",
    "delivered_at", "completed_at", "accepted_by", "assigned_driver_id", "facility_id",
    "item_count", "requested_pickup_time", "recipient_name", "recipient_phone"
}

REVEALED_JOB_STATUSES = {"accepted", "in_progress", "picked_up", "in_transit", "delivered", "completed", "returned"}

def scoped_job(job: dict, user: dict) -> dict:
    if user.get("role") != "driver":
        return job
    j = {k: v for k, v in job.items() if k in DRIVER_JOB_FIELDS}
    j["pickup_area"] = address_area(job.get("pickup_address"), job.get("pickup_city"))
    j["dropoff_area"] = address_area(job.get("delivery_address") or job.get("dropoff_address"), job.get("delivery_city"))
    assigned_to_me = user["id"] in (job.get("accepted_by"), job.get("assigned_driver_id"))
    if not (assigned_to_me and job.get("status") in REVEALED_JOB_STATUSES):
        j["pickup_address"] = None
        j["delivery_address"] = None
        j["dropoff_address"] = None
        j["recipient_name"] = None
        j["recipient_phone"] = None
    return j

def address_area(address: Optional[str], city: Optional[str] = None) -> str:
    if not address:
        return city or ""
    parts = [p.strip() for p in address.split(",")]
    street = re.sub(r"^[\d\-#]+[A-Za-z]?\s+", "", parts[0]).strip() or parts[0]
    locality = city or (parts[1] if len(parts) > 1 else "")
    return f"{street}, {locality}" if locality and locality.lower() != street.lower() else street

async def log_audit(actor: dict, action: str, entity: str, entity_id: str, details: Optional[dict] = None):
    try:
        entry = {
            "id": str(uuid.uuid4()),
            "actor_id": actor["id"],
            "actor_role": actor.get("role"),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if details:
            entry["details"] = details
        await db.audit_logs.insert_one(entry)
    except Exception as e:
        logging.getLogger(__name__).error(f"Audit log write failed: {e}")

async def log_view_once(actor: dict, entity: str, entity_id: str):
    """Log a 'view' audit event, deduped per actor/entity within 10 minutes."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        recent = await db.audit_logs.find_one({
            "actor_id": actor["id"], "action": "view", "entity": entity,
            "entity_id": entity_id, "timestamp": {"$gte": cutoff}
        }, {"_id": 1})
        if not recent:
            await log_audit(actor, "view", entity, entity_id)
    except Exception as e:
        logging.getLogger(__name__).error(f"View log failed: {e}")

def insurance_flag_of(insurance_expiry: Optional[str]) -> Optional[str]:
    """Returns 'expired', 'expiring_soon' (<=30 days) or None."""
    if not insurance_expiry:
        return None
    try:
        expiry = datetime.fromisoformat(insurance_expiry[:10]).date()
    except ValueError:
        return None
    today = datetime.now(timezone.utc).date()
    if expiry < today:
        return "expired"
    if (expiry - today).days <= 30:
        return "expiring_soon"
    return None

def driver_compliance_issues(rec: dict) -> list:
    issues = []
    status = rec.get("verification_status", "incomplete")
    if status != "approved":
        issues.append(f"verification {status}")
    if insurance_flag_of(rec.get("insurance_expiry")) == "expired":
        issues.append("insurance expired")
    return issues

async def is_driver_verified(user_id: str) -> bool:
    """Compliance gate for NEW work (offers/assignments/accepts). Active deliveries are not re-checked."""
    rec = await db.drivers.find_one({"user_id": user_id}, {"_id": 0, "verification_status": 1, "insurance_expiry": 1})
    return bool(rec) and not driver_compliance_issues(rec)

async def facility_ids_owned_by(user_id: str) -> list:
    return [f["id"] async for f in db.facilities.find({"owner_user_id": user_id}, {"_id": 0, "id": 1})]

def strip_facility_billing(fac: dict, user: dict) -> dict:
    if user.get("role") in STAFF_ROLES or fac.get("owner_user_id") == user["id"]:
        return fac
    return {k: v for k, v in fac.items() if k != "billing_email"}

async def driver_verification_of(user: dict) -> Optional[str]:
    if user.get("role") != "driver":
        return None
    rec = await db.drivers.find_one({"user_id": user["id"]}, {"_id": 0, "verification_status": 1})
    return rec.get("verification_status", "incomplete") if rec else "incomplete"

# ---- Emergent Object Storage (driver documents) ----
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
STORAGE_APP_PREFIX = "meditrans"
storage_key = None

def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

def del_object(path: str):
    key = init_storage()
    requests.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=30)

async def cascade_delete_driver_data(user_id: str):
    docs = await db.driver_documents.find({"user_id": user_id}, {"_id": 0, "storage_path": 1}).to_list(50)
    for d in docs:
        try:
            await asyncio.to_thread(del_object, d["storage_path"])
        except Exception as e:
            logging.getLogger(__name__).warning(f"Storage blob delete failed: {e}")
    await db.driver_documents.delete_many({"user_id": user_id})
    await db.drivers.delete_one({"user_id": user_id})

# ---- Driver onboarding document registry ----
DRIVER_DOC_TYPES = {
    "drivers_licence": {"label": "Driver's Licence", "required": True},
    "vehicle_registration": {"label": "Vehicle Registration + Plate", "required": True},
    "cvor": {"label": "CVOR Status", "required": True},
    "tdg_certificate": {"label": "TDG Training Certificate", "required": True},
    "vulnerable_sector_check": {"label": "Vulnerable Sector Check", "required": True},
    "commercial_insurance": {"label": "Commercial Insurance (min $2M liability)", "required": True, "needs_expiry": True},
    "cold_chain_cert": {"label": "Cold-Chain Handling Certification", "required": False, "unlocks": "cold_chain jobs"},
}
DOC_STATUSES = {"missing", "pending", "approved", "rejected"}
DOC_TO_DRIVER_FIELD = {
    "cvor": "cvor_status",
    "tdg_certificate": "tdg_cert_status",
    "vulnerable_sector_check": "vulnerable_sector_check_status",
    "commercial_insurance": "insurance_status",
}
ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf", "image/heic"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

async def ensure_driver_record(user_id: str) -> dict:
    rec = await db.drivers.find_one({"user_id": user_id}, {"_id": 0})
    if rec:
        return rec
    rec = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "vehicle_type": None,
        "vehicle_plate": None,
        "cvor_status": "not_submitted",
        "tdg_cert_status": "not_submitted",
        "vulnerable_sector_check_status": "not_submitted",
        "insurance_status": "not_submitted",
        "insurance_expiry": None,
        "cold_chain_certified": False,
        "verification_status": "incomplete",
        "rating_avg": 0.0,
        "total_trips": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.drivers.insert_one(rec)
    rec.pop("_id", None)
    return rec

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
        "status": "approved",
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
            created_at=user_doc["created_at"],
            verification_status="incomplete" if role == "driver" else None
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
            created_at=user["created_at"],
            verification_status=await driver_verification_of(user)
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
        created_at=current_user["created_at"],
        verification_status=await driver_verification_of(current_user)
    )

@api_router.post("/auth/change-password")
async def change_password(payload: PasswordChange, current_user: dict = Depends(get_current_user)):
    if not verify_password(payload.current_password, current_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from current")
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}}
    )
    return {"status": "ok", "message": "Password updated"}

# ======================
# Forgot / Reset Password
# ======================
RESET_TOKEN_EXPIRY_HOURS = 1

def _render_reset_email(full_name: str, reset_link: str) -> str:
    safe_name = (full_name or "there").split(" ")[0]
    return f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f8fafc;margin:0;padding:40px 20px;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="max-width:520px;width:100%;background:#ffffff;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <tr><td style="padding:32px 32px 16px;text-align:left;">
      <div style="display:inline-block;width:40px;height:40px;background:#2563eb;border-radius:8px;vertical-align:middle;"></div>
      <span style="font-family:-apple-system,Segoe UI,Arial;font-weight:700;font-size:20px;color:#0f172a;margin-left:10px;vertical-align:middle;">MediTrans</span>
    </td></tr>
    <tr><td style="padding:0 32px;">
      <h1 style="font-size:24px;color:#0f172a;margin:8px 0 16px;">Reset your password</h1>
      <p style="color:#475569;font-size:15px;line-height:1.55;">Hi {safe_name}, we got a request to reset your MediTrans password. Click the button below to set a new one. This link expires in {RESET_TOKEN_EXPIRY_HOURS} hour.</p>
      <p style="text-align:center;margin:28px 0;">
        <a href="{reset_link}" style="background:#2563eb;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:600;display:inline-block;">Reset Password</a>
      </p>
      <p style="color:#64748b;font-size:13px;line-height:1.5;">If the button doesn't work, copy this link into your browser:<br><a href="{reset_link}" style="color:#2563eb;word-break:break-all;">{reset_link}</a></p>
      <p style="color:#94a3b8;font-size:12px;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;">Didn't request this? You can safely ignore this email — your password won't change unless you click the link above.</p>
    </td></tr>
    <tr><td style="padding:24px 32px;color:#94a3b8;font-size:12px;text-align:center;">MediTrans Ontario — medical transport for professionals.</td></tr>
  </table>
</body></html>"""

@api_router.post("/auth/forgot-password")
async def forgot_password(req: PasswordResetRequest, request: Request):
    """Request a password-reset email. Always returns 200 regardless of whether the email
    exists, to prevent user enumeration."""
    user = await db.users.find_one({"email": req.email.lower().strip()}, {"_id": 0})
    if not user:
        # Don't leak whether the email is registered
        return {"status": "ok", "message": "If the email is registered, a reset link has been sent."}

    # Sign a short-lived JWT bound to the user's current password_hash — this means once the
    # user resets their password, the token automatically becomes invalid (single-use in practice).
    ph_checksum = hashlib.sha256(user["password_hash"].encode()).hexdigest()[:16]
    token = jwt.encode({
        "user_id": user["id"],
        "purpose": "password_reset",
        "ph": ph_checksum,
        "exp": datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Prefer explicit env; fallback to the request origin
    origin = RESET_LINK_BASE_URL or str(request.headers.get("origin", "")).rstrip('/') or str(request.base_url).rstrip('/')
    reset_link = f"{origin}/reset-password?token={token}"

    if not RESEND_API_KEY:
        # No provider configured — log and still return 200 so the flow keeps working
        logger.warning(f"[forgot-password] RESEND_API_KEY not set; reset link for {user['email']}: {reset_link}")
        return {"status": "ok", "message": "If the email is registered, a reset link has been sent.",
                "dev_reset_link": reset_link}

    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [user["email"]],
            "subject": "Reset your MediTrans password",
            "html": _render_reset_email(user.get("full_name", ""), reset_link)
        }
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"[forgot-password] reset email sent to {user['email']} (id={result.get('id')})")
    except Exception as e:
        logger.error(f"[forgot-password] Resend error: {e}")
        # Don't expose the error to the client
    return {"status": "ok", "message": "If the email is registered, a reset link has been sent."}

@api_router.post("/auth/reset-password")
async def reset_password(payload: PasswordResetConfirm):
    """Consume a reset token and set a new password."""
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    try:
        claims = jwt.decode(payload.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Reset link has expired — request a new one")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid reset link")
    if claims.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset link")
    user = await db.users.find_one({"id": claims.get("user_id")}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="User no longer exists")
    # Single-use: token is bound to the password_hash at issue time. Any successful reset
    # changes the hash and invalidates outstanding tokens for that user.
    current_ph_checksum = hashlib.sha256(user["password_hash"].encode()).hexdigest()[:16]
    if claims.get("ph") != current_ph_checksum:
        raise HTTPException(status_code=400, detail="Reset link has already been used")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}}
    )
    return {"status": "ok", "message": "Password reset successfully"}

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
    permits = await db.permits.find({}, {"_id": 0}).sort("order", 1).to_list(1000)
    return {"permits": permits}

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
            "ledger_count": str(len(owed_ids))
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
    """Finalize a paid payment_transaction: settle owed ledger entries OR credit a tip to driver earnings."""
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx or tx.get("payment_status") != "paid":
        return
    payment_type = tx.get("payment_type")
    now_iso = datetime.now(timezone.utc).isoformat()

    if payment_type == "balance":
        ledger_ids = tx.get("ledger_ids") or []
        if ledger_ids:
            await db.ledger.update_many(
                {"id": {"$in": ledger_ids}, "status": "owed"},
                {"$set": {"status": "paid", "paid_at": now_iso, "payment_session_id": session_id}}
            )
    elif payment_type == "tip":
        # Credit 100% of tip to the driver's earnings (no platform commission on tips)
        existing = await db.earnings.find_one({"payment_session_id": session_id}, {"_id": 0})
        if existing:
            return  # idempotent — already credited
        await db.earnings.insert_one({
            "id": str(uuid.uuid4()),
            "driver_id": tx.get("driver_id"),
            "job_id": tx.get("job_id"),
            "type": "tip",
            "amount": float(tx.get("amount", 0)),
            "tipper_name": tx.get("tipper_name"),
            "payment_session_id": session_id,
            "created_at": now_iso
        })

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

# ======================
# Tip Your Driver (public)
# ======================
class TipCheckoutRequest(BaseModel):
    amount: float
    origin_url: str
    tipper_name: Optional[str] = None

@api_router.get("/tips/info/{job_id}")
async def get_tip_info(job_id: str):
    """Public — no auth. Returns job summary + driver info so customer can decide how much to tip."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Trip not found")
    if job.get("status") not in ("completed", "delivered"):
        raise HTTPException(status_code=400, detail="Tips can only be sent for completed trips")
    driver_id = job.get("accepted_by")
    driver = await db.users.find_one({"id": driver_id}, {"_id": 0, "password_hash": 0}) if driver_id else None
    # Minimum tip = $1
    offered = float(job.get("offered_price", 0))
    presets = [
        {"label": "15%", "amount": round(offered * 0.15, 2)},
        {"label": "20%", "amount": round(offered * 0.20, 2)},
        {"label": "25%", "amount": round(offered * 0.25, 2)},
    ]
    # Already tipped?
    existing_tips = await db.earnings.find(
        {"job_id": job_id, "type": "tip"}, {"_id": 0}
    ).to_list(100)
    return {
        "trip": {
            "id": job["id"],
            "title": job["title"],
            "pickup_city": job["pickup_city"],
            "delivery_city": job["delivery_city"],
            "offered_price": offered,
            "completed_at": job.get("completed_at")
        },
        "driver": {
            "full_name": driver["full_name"] if driver else "Driver",
            "first_name": (driver["full_name"].split(" ")[0] if driver else "Driver")
        },
        "presets": presets,
        "currency": "CAD",
        "already_tipped_total": round(sum(t.get("amount", 0) for t in existing_tips), 2)
    }

@api_router.post("/tips/checkout/{job_id}")
async def create_tip_checkout(job_id: str, req: TipCheckoutRequest, request: Request):
    """Public — no auth. Creates a Stripe Checkout for a tip. If driver has completed Stripe Connect
    onboarding, the tip is routed directly to their connected account (destination charge, 100% to driver).
    Otherwise the tip goes to the platform account and is credited to driver earnings on webhook."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Tip amount must be positive")
    if req.amount > 10000:
        raise HTTPException(status_code=400, detail="Tip amount exceeds maximum ($10,000)")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Trip not found")
    if job.get("status") not in ("completed", "delivered"):
        raise HTTPException(status_code=400, detail="Tips can only be sent for completed trips")
    driver_id = job.get("accepted_by")
    if not driver_id:
        raise HTTPException(status_code=400, detail="No driver on this trip")

    driver = await db.users.find_one({"id": driver_id}, {"_id": 0})
    amount = round(float(req.amount), 2)
    amount_cents = int(round(amount * 100))

    success_url = f"{req.origin_url}/tip/{job_id}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{req.origin_url}/tip/{job_id}"

    # If driver is fully onboarded with Connect, use destination charge (split at source)
    connect_account_id = driver.get("stripe_account_id") if driver else None
    connect_charges_enabled = bool(driver and driver.get("stripe_charges_enabled"))
    use_connect = bool(connect_account_id and connect_charges_enabled)

    try:
        if use_connect:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": "cad",
                        "product_data": {"name": f"Tip for {driver['full_name']}", "description": f"Trip: {job['title']}"},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                payment_intent_data={
                    # Destination charge — 100% of tip routed to driver's connected account
                    "transfer_data": {"destination": connect_account_id},
                    "description": f"MediTrans tip — {job['title']}",
                },
                metadata={
                    "job_id": job_id,
                    "driver_id": driver_id,
                    "payment_type": "tip",
                    "tipper_name": (req.tipper_name or "")[:80],
                    "connect": "true"
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            checkout_url = session.url
            session_id = session.id
        else:
            # Fallback: platform captures funds, driver earnings credited via webhook/status poll
            host_url = str(request.base_url).rstrip('/')
            webhook_url = f"{host_url}/api/webhook/stripe"
            emergent_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
            emergent_req = CheckoutSessionRequest(
                amount=amount,
                currency="cad",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "job_id": job_id,
                    "driver_id": driver_id,
                    "payment_type": "tip",
                    "tipper_name": (req.tipper_name or "")[:80],
                    "connect": "false"
                }
            )
            em_session: CheckoutSessionResponse = await emergent_checkout.create_checkout_session(emergent_req)
            checkout_url = em_session.url
            session_id = em_session.session_id
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "payment_type": "tip",
        "job_id": job_id,
        "driver_id": driver_id,
        "tipper_name": req.tipper_name,
        "amount": amount,
        "currency": "cad",
        "status": "pending",
        "payment_status": "initiated",
        "connect_routed": use_connect,
        "stripe_account_id": connect_account_id if use_connect else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })

    return {"checkout_url": checkout_url, "session_id": session_id, "amount": amount, "routed_to_driver": use_connect}

@api_router.get("/tips/status/{session_id}")
async def get_tip_status(session_id: str, request: Request):
    """Public — no auth. Lets the tipper poll payment status after redirect."""
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    try:
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if tx and tx.get("payment_type") == "tip" and tx.get("payment_status") != "paid" and status.payment_status == "paid":
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

@api_router.get("/driver/tips")
async def get_driver_tips(current_user: dict = Depends(get_current_user)):
    tips = await db.earnings.find(
        {"driver_id": current_user["id"], "type": "tip"}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    total = round(sum(t.get("amount", 0) for t in tips), 2)
    return {"tips": tips, "total": total, "count": len(tips), "currency": "CAD"}

@api_router.get("/driver/earnings")
async def driver_earnings(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("driver", "admin"):
        raise HTTPException(status_code=403, detail="Driver access required")
    me = current_user["id"]
    jobs = await db.jobs.find(
        {"$or": [{"accepted_by": me}, {"assigned_driver_id": me}],
         "status": {"$in": ["completed", "delivered", "returned"]}},
        {"_id": 0}
    ).sort("completed_at", -1).to_list(500)
    ledger = await db.ledger.find({"driver_id": me}, {"_id": 0}).to_list(2000)
    commission_by_job = {}
    cancellation_fees = []
    for e in ledger:
        if e.get("type") == "commission":
            commission_by_job[e.get("job_id")] = commission_by_job.get(e.get("job_id"), 0) + float(e.get("amount", 0))
        elif e.get("type") == "cancellation_fee":
            cancellation_fees.append(e)

    fees_cfg = await get_fees_from_db()
    commission_rate = float(fees_cfg.get("commission_rate", 0.20))

    # Current pay period: Monday 00:00 UTC of this week
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    period_start_iso = period_start.isoformat()

    trips = []
    lifetime_gross = lifetime_commission = 0.0
    period_gross = period_commission = 0.0
    for j in jobs:
        gross = float(j.get("payout_amount") or j.get("offered_price") or 0)
        if j.get("status") == "returned":
            trips.append({
                "job_id": j["id"], "title": j.get("title"), "item_category": j.get("item_category"),
                "pickup_city": j.get("pickup_city"), "delivery_city": j.get("delivery_city"),
                "status": "returned", "completed_at": j.get("delivered_at") or j.get("completed_at") or j.get("created_at"),
                "gross": 0.0, "commission": 0.0, "net": 0.0
            })
            continue
        commission = round(commission_by_job.get(j["id"], gross * commission_rate), 2)
        net = round(gross - commission, 2)
        done_at = j.get("completed_at") or j.get("delivered_at")
        trips.append({
            "job_id": j["id"], "title": j.get("title"), "item_category": j.get("item_category"),
            "pickup_city": j.get("pickup_city"), "delivery_city": j.get("delivery_city"),
            "status": j.get("status"), "completed_at": done_at,
            "gross": gross, "commission": commission, "net": net
        })
        lifetime_gross += gross
        lifetime_commission += commission
        if done_at and done_at >= period_start_iso:
            period_gross += gross
            period_commission += commission

    period_fees = sum(float(f.get("amount", 0)) for f in cancellation_fees if f.get("created_at", "") >= period_start_iso)
    lifetime_fees = sum(float(f.get("amount", 0)) for f in cancellation_fees)

    rec = await db.drivers.find_one({"user_id": me}, {"_id": 0})
    rating = await _compute_driver_rating(me)
    return {
        "trips": trips,
        "cancellation_fees": sorted(cancellation_fees, key=lambda f: f.get("created_at", ""), reverse=True),
        "commission_rate": commission_rate,
        "period": {
            "start": period_start_iso,
            "gross": round(period_gross, 2),
            "commission": round(period_commission, 2),
            "cancellation_fees": round(period_fees, 2),
            "net": round(period_gross - period_commission - period_fees, 2),
            "trip_count": sum(1 for t in trips if t["status"] != "returned" and (t["completed_at"] or "") >= period_start_iso)
        },
        "lifetime": {
            "total_trips": (rec or {}).get("total_trips", 0),
            "rating_avg": rating["avg"],
            "rating_count": rating["count"],
            "gross": round(lifetime_gross, 2),
            "commission": round(lifetime_commission, 2),
            "cancellation_fees": round(lifetime_fees, 2),
            "net": round(lifetime_gross - lifetime_commission - lifetime_fees, 2)
        },
        "currency": "CAD"
    }

# ======================
# Driver Ratings & Reviews
# ======================
async def _compute_driver_rating(driver_id: str) -> dict:
    reviews = await db.reviews.find(
        {"driver_id": driver_id, "hidden": {"$ne": True}}, {"_id": 0}
    ).to_list(10000)
    count = len(reviews)
    if count == 0:
        return {"avg": 0.0, "count": 0}
    avg = sum(r["rating"] for r in reviews) / count
    return {"avg": round(avg, 2), "count": count}

@api_router.get("/reviews/info/{job_id}")
async def get_review_info(job_id: str):
    """Public — checks if a trip can still be reviewed."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Trip not found")
    if job.get("status") not in ("completed", "delivered"):
        raise HTTPException(status_code=400, detail="Only completed trips can be reviewed")
    driver = await db.users.find_one({"id": job.get("accepted_by")}, {"_id": 0, "password_hash": 0})
    existing = await db.reviews.find_one({"job_id": job_id}, {"_id": 0})
    rating_summary = await _compute_driver_rating(job.get("accepted_by"))
    return {
        "trip": {
            "id": job["id"],
            "title": job["title"],
            "pickup_city": job["pickup_city"],
            "delivery_city": job["delivery_city"]
        },
        "driver": {
            "full_name": driver["full_name"] if driver else "Driver",
            "first_name": (driver["full_name"].split(" ")[0] if driver else "Driver")
        },
        "already_reviewed": existing is not None,
        "driver_rating": rating_summary
    }

@api_router.post("/reviews/{job_id}")
async def submit_review(job_id: str, review: ReviewCreate):
    """Public — customer submits a 1-5 rating + optional comment for a completed trip."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Trip not found")
    if job.get("status") not in ("completed", "delivered"):
        raise HTTPException(status_code=400, detail="Only completed trips can be reviewed")
    driver_id = job.get("accepted_by")
    if not driver_id:
        raise HTTPException(status_code=400, detail="No driver on this trip")
    # One review per job
    if await db.reviews.find_one({"job_id": job_id}):
        raise HTTPException(status_code=400, detail="This trip has already been reviewed")

    comment = (review.comment or "").strip()[:2000] or None
    reviewer_name = (review.reviewer_name or "").strip()[:80] or None

    doc = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "driver_id": driver_id,
        "rating": int(review.rating),
        "comment": comment,
        "reviewer_name": reviewer_name,
        "hidden": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.reviews.insert_one(doc)
    doc.pop("_id", None)
    return {"review": doc, "driver_rating": await _compute_driver_rating(driver_id)}

@api_router.get("/drivers/{driver_id}/reviews")
async def public_driver_reviews(driver_id: str):
    """Public — list of visible reviews + summary for a driver."""
    reviews = await db.reviews.find(
        {"driver_id": driver_id, "hidden": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {
        "reviews": reviews,
        "summary": await _compute_driver_rating(driver_id)
    }

@api_router.get("/driver/reviews")
async def get_my_reviews(current_user: dict = Depends(get_current_user)):
    reviews = await db.reviews.find(
        {"driver_id": current_user["id"], "hidden": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {
        "reviews": reviews,
        "summary": await _compute_driver_rating(current_user["id"])
    }

# ======================
# Stripe Connect (Express) — driver payouts
# ======================
class ConnectOnboardRequest(BaseModel):
    origin_url: str

@api_router.post("/driver/connect/onboard")
async def start_connect_onboarding(req: ConnectOnboardRequest, current_user: dict = Depends(get_current_user)):
    """Create (or reuse) a Stripe Express account for the driver and return an onboarding link."""
    try:
        account_id = current_user.get("stripe_account_id")
        if not account_id:
            acct = stripe.Account.create(
                type="express",
                country="CA",
                email=current_user["email"],
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True}
                },
                business_type="individual",
                business_profile={
                    "product_description": "Medical transportation services in Ontario, Canada",
                    "mcc": "4789"  # Transportation Services - Not Elsewhere Classified
                },
                metadata={"user_id": current_user["id"]}
            )
            account_id = acct.id
            await db.users.update_one(
                {"id": current_user["id"]},
                {"$set": {
                    "stripe_account_id": account_id,
                    "stripe_charges_enabled": False,
                    "stripe_payouts_enabled": False,
                    "stripe_details_submitted": False
                }}
            )

        account_link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=f"{req.origin_url}/billing?stripe_refresh=1",
            return_url=f"{req.origin_url}/billing?stripe_return=1",
            type="account_onboarding"
        )
        return {"url": account_link.url, "account_id": account_id}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

@api_router.get("/driver/connect/status")
async def get_connect_status(current_user: dict = Depends(get_current_user)):
    """Return Stripe Connect onboarding status for the current driver; syncs flags from Stripe."""
    account_id = current_user.get("stripe_account_id")
    if not account_id:
        return {
            "connected": False,
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": False,
            "account_id": None
        }
    try:
        acct = stripe.Account.retrieve(account_id)
        # Sync latest Stripe-side flags into our user doc
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {
                "stripe_charges_enabled": bool(acct.charges_enabled),
                "stripe_payouts_enabled": bool(acct.payouts_enabled),
                "stripe_details_submitted": bool(acct.details_submitted)
            }}
        )
        return {
            "connected": True,
            "charges_enabled": bool(acct.charges_enabled),
            "payouts_enabled": bool(acct.payouts_enabled),
            "details_submitted": bool(acct.details_submitted),
            "account_id": account_id,
            "requirements": {
                "currently_due": list(acct.requirements.currently_due or []),
                "past_due": list(acct.requirements.past_due or []),
                "disabled_reason": acct.requirements.disabled_reason
            }
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

@api_router.post("/driver/connect/login-link")
async def create_connect_login_link(current_user: dict = Depends(get_current_user)):
    """Generate a one-time link to the driver's Stripe Express dashboard."""
    account_id = current_user.get("stripe_account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="No Stripe account connected yet")
    try:
        link = stripe.Account.create_login_link(account_id)
        return {"url": link.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

# Job Routes
@api_router.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") == "driver":
        raise HTTPException(status_code=403, detail="Drivers cannot post jobs")
    data = job.model_dump()
    validate_enum(data.get("item_category"), ITEM_CATEGORIES, "item_category")
    validate_handling_flags(data.get("handling_flags"))
    # sync legacy <-> marketplace field aliases
    dropoff = data.get("delivery_address") or data.get("dropoff_address")
    if not dropoff:
        raise HTTPException(status_code=422, detail="delivery_address or dropoff_address is required")
    data["delivery_address"] = dropoff
    data["dropoff_address"] = dropoff
    distance = data.get("distance_km") if data.get("distance_km") is not None else data.get("estimated_distance_km")
    data["distance_km"] = distance
    data["estimated_distance_km"] = distance if distance is not None else 0
    payout = data.get("payout_amount") if data.get("payout_amount") is not None else data.get("offered_price")
    if payout is None:
        raise HTTPException(status_code=422, detail="payout_amount or offered_price is required")
    data["payout_amount"] = payout
    data["offered_price"] = payout
    if data.get("facility_id"):
        facility = await db.facilities.find_one({"id": data["facility_id"]}, {"_id": 0})
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")
    job_id = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        **data,
        "status": "open",
        "posted_by": current_user["id"],
        "accepted_by": None,
        "assigned_driver_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "accepted_at": None,
        "completed_at": None,
        "picked_up_at": None,
        "delivered_at": None
    }
    await db.jobs.insert_one(job_doc)
    await log_audit(current_user, "create", "job", job_id)
    return JobResponse(**job_doc)

@api_router.get("/jobs")
async def get_jobs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role in STAFF_ROLES:
        query = {}
    elif role == "facility":
        fac_ids = await facility_ids_owned_by(current_user["id"])
        query = {"$or": [{"posted_by": current_user["id"]}, {"facility_id": {"$in": fac_ids}}]}
    else:
        query = {"$or": [{"status": "open"}, {"accepted_by": current_user["id"]}, {"assigned_driver_id": current_user["id"]}]}
    if status:
        query = {"$and": [query, {"status": status}]} if query else {"status": status}

    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    await log_audit(current_user, "view", "job", "list")
    return {"jobs": [scoped_job(j, current_user) for j in jobs]}

@api_router.get("/jobs/available")
async def get_available_jobs(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role == "facility":
        fac_ids_owned = await facility_ids_owned_by(current_user["id"])
        query = {"status": "open", "$or": [{"posted_by": current_user["id"]}, {"facility_id": {"$in": fac_ids_owned}}]}
    elif role == "driver":
        me = current_user["id"]
        query = {"$or": [
            {"status": "open", "declined_by": {"$ne": me}},
            {"status": "offered", "assigned_driver_id": None, "declined_by": {"$ne": me}},
            {"status": "offered", "assigned_driver_id": me}
        ]}
        rec = await db.drivers.find_one({"user_id": me}, {"_id": 0, "cold_chain_certified": 1})
        if not (rec and rec.get("cold_chain_certified")):
            query = {"$and": [query, {"handling_flags": {"$ne": "cold_chain"}}, {"temperature_controlled": {"$ne": True}}]}
    else:
        query = {"status": "open"}
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    fac_ids = list({j["facility_id"] for j in jobs if j.get("facility_id")})
    fac_names = {}
    if fac_ids:
        async for f in db.facilities.find({"id": {"$in": fac_ids}}, {"_id": 0, "id": 1, "name": 1}):
            fac_names[f["id"]] = f["name"]
    out = []
    for j in jobs:
        s = scoped_job(j, current_user)
        if j.get("facility_id"):
            s["facility_name"] = fac_names.get(j["facility_id"])
        out.append(s)
    await log_audit(current_user, "view", "job", "list")
    return {"jobs": out}

@api_router.get("/jobs/my")
async def get_my_jobs(current_user: dict = Depends(get_current_user)):
    jobs = await db.jobs.find(
        {"$or": [{"posted_by": current_user["id"]}, {"accepted_by": current_user["id"]}, {"assigned_driver_id": current_user["id"]}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    await log_audit(current_user, "view", "job", "list")
    return {"jobs": [scoped_job(j, current_user) for j in jobs]}

@api_router.post("/jobs/{job_id}/accept")
async def accept_job(job_id: str, current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role not in ("driver", "admin"):
        raise HTTPException(status_code=403, detail="Only drivers can accept jobs")
    if role == "driver" and not await is_driver_verified(current_user["id"]):
        raise HTTPException(status_code=403, detail="You are not currently eligible for new jobs — check your verification status and insurance expiry.")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    offered_to_me = job["status"] == "offered" and job.get("assigned_driver_id") in (None, current_user["id"])
    if job["status"] != "open" and not offered_to_me:
        raise HTTPException(status_code=400, detail="Job is no longer available")
    
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "accepted",
            "accepted_by": current_user["id"],
            "assigned_driver_id": current_user["id"],
            "accepted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    await log_audit(current_user, "accept", "job", job_id)
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": scoped_job(updated_job, current_user)}

@api_router.post("/jobs/{job_id}/decline")
async def decline_job(job_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can decline jobs")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") == "offered" and current_user["id"] in (job.get("assigned_driver_id"), job.get("accepted_by")):
        await db.jobs.update_one({"id": job_id}, {
            "$set": {"status": "open", "assigned_driver_id": None, "accepted_by": None},
            "$addToSet": {"declined_by": current_user["id"]}
        })
    elif job.get("status") == "open" or (job.get("status") == "offered" and not job.get("assigned_driver_id")):
        await db.jobs.update_one({"id": job_id}, {"$addToSet": {"declined_by": current_user["id"]}})
    else:
        raise HTTPException(status_code=400, detail="Job can no longer be declined")
    await log_audit(current_user, "decline", "job", job_id)
    return {"status": "declined", "job_id": job_id}

@api_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """Driver cancels a job they previously accepted.
    Within the grace window (default 5 min) it's free; after that a cancellation fee is charged."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") not in ("accepted", "in_progress"):
        raise HTTPException(status_code=400, detail="This job can no longer be cancelled — after pickup the item must be delivered or returned to the facility")
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
            "assigned_driver_id": None,
            "accepted_at": None,
            "last_cancelled_by": current_user["id"],
            "last_cancelled_at": now.isoformat()
        }}
    )
    await log_audit(current_user, "cancel", "job", job_id)
    
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
    if job.get("status") not in ("accepted", "in_progress", "picked_up", "in_transit"):
        raise HTTPException(status_code=400, detail="Only active jobs can be completed")
    
    now = datetime.now(timezone.utc)
    result = await settle_job_completion(job, current_user["id"], "completed")
    await log_audit(current_user, "complete", "job", job_id)
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {
        "job": updated_job,
        **result
    }

async def settle_job_completion(job: dict, driver_id: str, final_status: str = "completed") -> dict:
    now = datetime.now(timezone.utc)
    await db.jobs.update_one(
        {"id": job["id"]},
        {"$set": {
            "status": final_status,
            "completed_at": now.isoformat(),
            "delivered_at": now.isoformat()
        }}
    )
    await db.drivers.update_one({"user_id": driver_id}, {"$inc": {"total_trips": 1}})
    
    # Record gross earnings (what the driver charged the customer)
    gross = float(job.get("offered_price") or job.get("payout_amount") or 0)
    earnings_doc = {
        "id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "job_id": job["id"],
        "amount": gross,
        "created_at": now.isoformat()
    }
    await db.earnings.insert_one(earnings_doc)
    
    # Record platform commission as owed ledger entry
    fees = await get_fees_from_db()
    commission_rate = float(fees.get("commission_rate", 0.20))
    if job.get("facility_id"):
        fac = await db.facilities.find_one({"id": job["facility_id"]}, {"_id": 0, "commission_rate_override": 1})
        if fac and fac.get("commission_rate_override") is not None:
            commission_rate = float(fac["commission_rate_override"])
    commission_amount = round(gross * commission_rate, 2)
    ledger_entry = {
        "id": str(uuid.uuid4()),
        "driver_id": driver_id,
        "job_id": job["id"],
        "type": "commission",
        "amount": commission_amount,
        "status": "owed",
        "currency": "CAD",
        "description": f"{commission_rate * 100:.0f}% platform commission on trip ${gross:.2f}",
        "created_at": now.isoformat()
    }
    await db.ledger.insert_one(ledger_entry)
    return {
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
    in_progress_jobs = await db.jobs.count_documents({"status": {"$in": ["in_progress", "accepted", "picked_up", "in_transit"]}})
    completed_jobs = await db.jobs.count_documents({"status": {"$in": ["completed", "delivered"]}})

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
    await cascade_delete_driver_data(user_id)
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
    if data.get("status") and data["status"] not in JOB_STATUSES:
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
    await db.ledger.delete_many({"job_id": job_id, "type": "commission"})
    await db.earnings.delete_many({"job_id": job_id})
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

# Admin: Permit requirement management
@api_router.get("/admin/reviews")
async def admin_list_reviews(admin: dict = Depends(require_admin)):
    reviews = await db.reviews.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return {"reviews": reviews}

@api_router.delete("/admin/reviews/{review_id}")
async def admin_delete_review(review_id: str, admin: dict = Depends(require_admin)):
    result = await db.reviews.delete_one({"id": review_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "deleted", "review_id": review_id}

@api_router.post("/admin/reviews/{review_id}/hide")
async def admin_hide_review(review_id: str, admin: dict = Depends(require_admin)):
    """Soft-hide a review instead of deleting — preserves history."""
    result = await db.reviews.update_one({"id": review_id}, {"$set": {"hidden": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "hidden", "review_id": review_id}

@api_router.get("/admin/permits")
async def admin_list_permits(admin: dict = Depends(require_admin)):
    permits = await db.permits.find({}, {"_id": 0}).sort("order", 1).to_list(1000)
    return {"permits": permits}

@api_router.post("/admin/permits")
async def admin_create_permit(permit: PermitCreate, admin: dict = Depends(require_admin)):
    existing = await db.permits.find_one({"id": permit.id})
    if existing:
        raise HTTPException(status_code=400, detail="Permit id already exists")
    count = await db.permits.count_documents({})
    doc = {**permit.model_dump(), "order": count + 1,
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.permits.insert_one(doc)
    doc.pop("_id", None)
    return {"permit": doc}

@api_router.put("/admin/permits/{permit_id}")
async def admin_update_permit(permit_id: str, update: PermitUpdate, admin: dict = Depends(require_admin)):
    existing = await db.permits.find_one({"id": permit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Permit not found")
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    if data:
        await db.permits.update_one({"id": permit_id}, {"$set": data})
    updated = await db.permits.find_one({"id": permit_id}, {"_id": 0})
    return {"permit": updated}

@api_router.delete("/admin/permits/{permit_id}")
async def admin_delete_permit(permit_id: str, admin: dict = Depends(require_admin)):
    result = await db.permits.delete_one({"id": permit_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Permit not found")
    return {"status": "deleted", "permit_id": permit_id}

# ---- Marketplace CRUD: Users (admin) ----
def user_public(u: dict) -> dict:
    u = {k: v for k, v in u.items() if k not in ("password_hash", "_id")}
    u.setdefault("name", u.get("full_name"))
    return u

@api_router.post("/users", status_code=201)
async def admin_create_user(payload: MarketplaceUserCreate, admin: dict = Depends(require_admin)):
    validate_enum(payload.role, USER_ROLES, "role")
    validate_enum(payload.status, USER_STATUSES, "status")
    if await db.users.find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "id": str(uuid.uuid4()),
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "full_name": payload.name,
        "name": payload.name,
        "phone": payload.phone,
        "role": payload.role,
        "status": payload.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "driver_profile": None
    }
    await db.users.insert_one(doc)
    return user_public(doc)

@api_router.get("/users")
async def admin_list_users(role: Optional[str] = None, status: Optional[str] = None, admin: dict = Depends(require_admin)):
    query = {}
    if role:
        query["role"] = role
    if status:
        query["status"] = status
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return {"users": [user_public(u) for u in users]}

@api_router.get("/users/{user_id}")
async def admin_get_user(user_id: str, admin: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_public(user)

@api_router.put("/users/{user_id}")
async def admin_update_user(user_id: str, payload: MarketplaceUserUpdate, admin: dict = Depends(require_admin)):
    validate_enum(payload.role, USER_ROLES, "role")
    validate_enum(payload.status, USER_STATUSES, "status")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "name" in updates:
        updates["full_name"] = updates["name"]
    result = await db.users.update_one({"id": user_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return user_public(user)

@api_router.delete("/users/{user_id}")
async def admin_delete_user_v2(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await cascade_delete_driver_data(user_id)
    return {"status": "deleted", "user_id": user_id}

# ---- Marketplace CRUD: Drivers (extends a user) ----
def validate_driver_fields(payload):
    for f in ("cvor_status", "tdg_cert_status", "vulnerable_sector_check_status", "insurance_status"):
        validate_enum(getattr(payload, f, None), COMPLIANCE_STATUSES, f)
    validate_enum(getattr(payload, "verification_status", None), DRIVER_VERIFICATION_STATUSES, "verification_status")

@api_router.post("/drivers", status_code=201)
async def create_driver_record(payload: DriverRecordCreate, current_user: dict = Depends(get_current_user)):
    validate_driver_fields(payload)
    target_user_id = payload.user_id if (payload.user_id and current_user.get("role") == "admin") else current_user["id"]
    target = await db.users.find_one({"id": target_user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if await db.drivers.find_one({"user_id": target_user_id}):
        raise HTTPException(status_code=400, detail="Driver record already exists for this user")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": target_user_id,
        **{k: v for k, v in payload.model_dump().items() if k != "user_id"},
        "rating_avg": 0.0,
        "total_trips": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.drivers.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/drivers")
async def list_driver_records(verification_status: Optional[str] = None, staff: dict = Depends(require_staff)):
    query = {}
    if verification_status:
        query["verification_status"] = verification_status
    drivers = await db.drivers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"drivers": drivers}

@api_router.get("/drivers/{user_id}/record")
async def get_driver_record(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["id"] != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    driver = await db.drivers.find_one({"user_id": user_id}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver record not found")
    return driver

@api_router.put("/drivers/{user_id}/record")
async def update_driver_record(user_id: str, payload: DriverRecordUpdate, current_user: dict = Depends(get_current_user)):
    is_admin = current_user.get("role") == "admin"
    if current_user["id"] != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    validate_driver_fields(payload)
    clearable = {"vehicle_type", "vehicle_plate", "insurance_expiry"}
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k in clearable}
    if not is_admin:
        for f in ("verification_status", "rating_avg", "total_trips"):
            updates.pop(f, None)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    prev = await db.drivers.find_one({"user_id": user_id}, {"_id": 0, "verification_status": 1})
    result = await db.drivers.update_one({"user_id": user_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver record not found")
    if "verification_status" in updates and prev and updates["verification_status"] != prev.get("verification_status"):
        await log_audit(current_user, "update", "driver_verification", user_id,
                        details={"from": prev.get("verification_status"), "to": updates["verification_status"]})
    return await db.drivers.find_one({"user_id": user_id}, {"_id": 0})

@api_router.delete("/drivers/{user_id}/record")
async def delete_driver_record(user_id: str, admin: dict = Depends(require_admin)):
    result = await db.drivers.delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Driver record not found")
    return {"status": "deleted", "user_id": user_id}

# ---- Marketplace CRUD: Facilities ----
@api_router.post("/facilities", status_code=201)
async def create_facility(payload: FacilityCreate, current_user: dict = Depends(get_current_user)):
    validate_enum(payload.type, FACILITY_TYPES, "type")
    validate_enum(payload.status, USER_STATUSES, "status")
    doc = {
        "id": str(uuid.uuid4()),
        **payload.model_dump(),
        "owner_user_id": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.facilities.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/facilities")
async def list_facilities(type: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if current_user.get("role") == "facility":
        query["owner_user_id"] = current_user["id"]
    if type:
        query["type"] = type
    if status:
        query["status"] = status
    facilities = await db.facilities.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"facilities": [strip_facility_billing(f, current_user) for f in facilities]}

@api_router.get("/facilities/{facility_id}")
async def get_facility(facility_id: str, current_user: dict = Depends(get_current_user)):
    facility = await db.facilities.find_one({"id": facility_id}, {"_id": 0})
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return strip_facility_billing(facility, current_user)

@api_router.put("/facilities/{facility_id}")
async def update_facility(facility_id: str, payload: FacilityUpdate, current_user: dict = Depends(get_current_user)):
    facility = await db.facilities.find_one({"id": facility_id}, {"_id": 0})
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.get("owner_user_id") != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    validate_enum(payload.type, FACILITY_TYPES, "type")
    validate_enum(payload.status, USER_STATUSES, "status")
    is_admin = current_user.get("role") == "admin"
    clearable = {"per_delivery_rate", "commission_rate_override"}
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k in clearable}
    if not is_admin:
        for f in ("status", "per_delivery_rate", "commission_rate_override"):
            updates.pop(f, None)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    changed = {k: {"from": facility.get(k), "to": v} for k, v in updates.items() if facility.get(k) != v}
    await db.facilities.update_one({"id": facility_id}, {"$set": updates})
    if changed:
        await log_audit(current_user, "update", "facility", facility_id, details=changed)
    return await db.facilities.find_one({"id": facility_id}, {"_id": 0})

@api_router.delete("/facilities/{facility_id}")
async def delete_facility(facility_id: str, current_user: dict = Depends(get_current_user)):
    facility = await db.facilities.find_one({"id": facility_id}, {"_id": 0})
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.get("owner_user_id") != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.facilities.delete_one({"id": facility_id})
    return {"status": "deleted", "facility_id": facility_id}

# ---- Marketplace CRUD: Jobs (read/update/delete by id) ----
@api_router.get("/jobs/{job_id}")
async def get_job_by_id(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    role = current_user.get("role")
    if role == "facility":
        fac_ids = await facility_ids_owned_by(current_user["id"])
        if job.get("posted_by") != current_user["id"] and job.get("facility_id") not in fac_ids:
            raise HTTPException(status_code=403, detail="Not authorized")
    elif role == "driver":
        if job.get("status") != "open" and current_user["id"] not in (job.get("accepted_by"), job.get("assigned_driver_id")):
            raise HTTPException(status_code=403, detail="Not authorized")
    await log_view_once(current_user, "job", job_id)
    return scoped_job(job, current_user)

@api_router.put("/jobs/{job_id}")
async def update_job(job_id: str, payload: JobUpdate, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    role = current_user.get("role")
    is_staff = role in STAFF_ROLES
    is_poster = job.get("posted_by") == current_user["id"]
    if role == "facility" and not is_poster:
        fac_ids = await facility_ids_owned_by(current_user["id"])
        is_poster = job.get("facility_id") in fac_ids
    is_assigned = current_user["id"] in (job.get("accepted_by"), job.get("assigned_driver_id"))
    if not (is_staff or is_poster or is_assigned):
        raise HTTPException(status_code=403, detail="Not authorized")
    raw_updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if role == "driver" and set(raw_updates.keys()) - {"status"}:
        raise HTTPException(status_code=403, detail="Drivers can only update job status")
    validate_enum(payload.status, JOB_STATUSES, "status")
    validate_enum(payload.item_category, ITEM_CATEGORIES, "item_category")
    validate_handling_flags(payload.handling_flags)
    updates = raw_updates
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    new_status = updates.get("status")
    target_driver = updates.get("assigned_driver_id") or job.get("assigned_driver_id") or job.get("accepted_by")
    if updates.get("assigned_driver_id") and not await is_driver_verified(updates["assigned_driver_id"]):
        raise HTTPException(status_code=400, detail="Cannot assign job: driver is not compliant (verification not approved, suspended, or insurance expired)")
    if new_status in ("offered", "accepted") and role != "driver":
        if not target_driver:
            raise HTTPException(status_code=400, detail="Assign a driver before offering the job")
        if not await is_driver_verified(target_driver):
            raise HTTPException(status_code=400, detail="Cannot offer job: driver is not compliant (verification not approved, suspended, or insurance expired)")
    if "dropoff_address" in updates:
        updates["delivery_address"] = updates["dropoff_address"]
    if "payout_amount" in updates:
        updates["offered_price"] = updates["payout_amount"]
    if "distance_km" in updates:
        updates["estimated_distance_km"] = updates["distance_km"]
    if "assigned_driver_id" in updates:
        effective_status = new_status or job.get("status")
        post_accept = effective_status in ("accepted", "in_progress", "picked_up", "in_transit", "delivered", "completed")
        updates["accepted_by"] = updates["assigned_driver_id"] if post_accept else None
    now = datetime.now(timezone.utc).isoformat()
    if new_status == "offered":
        updates["offered_at"] = now
    elif new_status == "cancelled":
        updates["cancelled_at"] = now
    if new_status == "accepted" and not job.get("accepted_at"):
        updates["accepted_at"] = now
        updates.setdefault("accepted_by", target_driver)
    elif new_status == "picked_up":
        updates["picked_up_at"] = now
    elif new_status in ("delivered", "completed"):
        updates["delivered_at"] = now
        updates["completed_at"] = now
    await db.jobs.update_one({"id": job_id}, {"$set": updates})
    await log_audit(current_user, "update", "job", job_id)
    updated = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return scoped_job(updated, current_user)

@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    allowed = job.get("posted_by") == current_user["id"] or current_user.get("role") == "admin"
    if not allowed and current_user.get("role") == "facility" and job.get("facility_id"):
        allowed = job["facility_id"] in await facility_ids_owned_by(current_user["id"])
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.jobs.delete_one({"id": job_id})
    await db.ledger.delete_many({"job_id": job_id, "type": "commission"})
    await db.earnings.delete_many({"job_id": job_id})
    await log_audit(current_user, "delete", "job", job_id)
    return {"status": "deleted", "job_id": job_id}

# ---- Chain of custody (legal, append-only) ----
async def assert_job_access(job: dict, user: dict):
    role = user.get("role")
    if role in STAFF_ROLES:
        return
    if role == "facility":
        fac_ids = await facility_ids_owned_by(user["id"])
        if job.get("posted_by") != user["id"] and job.get("facility_id") not in fac_ids:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        if user["id"] not in (job.get("accepted_by"), job.get("assigned_driver_id")):
            raise HTTPException(status_code=403, detail="Not authorized")

@api_router.post("/jobs/{job_id}/custody-events", status_code=201)
async def create_custody_event(job_id: str, payload: CustodyEventCreate, current_user: dict = Depends(get_current_user)):
    validate_enum(payload.event_type, CUSTODY_EVENT_TYPES, "event_type")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    role = current_user.get("role")
    if role == "facility":
        raise HTTPException(status_code=403, detail="Only the assigned driver or staff can record custody events")
    if role == "driver" and current_user["id"] not in (job.get("accepted_by"), job.get("assigned_driver_id")):
        raise HTTPException(status_code=403, detail="Only the assigned driver can record custody events for this job")

    et = payload.event_type
    status = job.get("status")
    if et == "pickup_confirmed":
        if status not in ("accepted", "in_progress"):
            raise HTTPException(status_code=400, detail="Pickup can only be confirmed on an accepted job")
        cl = payload.checklist or {}
        missing = []
        if not cl.get("label_confirmed"):
            missing.append("recipient name on label matches job")
        if not cl.get("item_count_confirmed"):
            missing.append("item count confirmed")
        cold = "cold_chain" in (job.get("handling_flags") or []) or job.get("temperature_controlled")
        if cold and not cl.get("cooler_confirmed"):
            missing.append("insulated cooler in use (required for cold chain)")
        if missing:
            raise HTTPException(status_code=400, detail=f"Pickup checklist incomplete: {'; '.join(missing)}")
    elif et == "in_transit_ping":
        if status not in ("picked_up", "in_transit"):
            raise HTTPException(status_code=400, detail="Transit pings require a picked-up job")
    elif et == "delivered":
        if status not in ("picked_up", "in_transit"):
            raise HTTPException(status_code=400, detail="Confirm pickup before marking delivered")
        if not payload.recipient_name:
            raise HTTPException(status_code=422, detail="recipient_name is required for delivery")
        if not payload.evidence_url:
            raise HTTPException(status_code=422, detail="Signature or ID evidence is required — items can never be left at the door")
    elif et == "delivery_attempted":
        if status not in ("picked_up", "in_transit"):
            raise HTTPException(status_code=400, detail="No active delivery to abort")
    elif et == "returned":
        if status not in ("picked_up", "in_transit"):
            raise HTTPException(status_code=400, detail="No active delivery to return")
        attempted = await db.custody_events.find_one({"job_id": job_id, "event_type": "delivery_attempted"}, {"_id": 0})
        if not attempted:
            raise HTTPException(status_code=400, detail="Log a delivery attempt before returning the item")

    doc = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        **payload.model_dump(),
        "actor_id": current_user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.custody_events.insert_one(doc)
    await log_audit(current_user, "create", "custody_event", doc["id"])
    doc.pop("_id", None)

    settlement = None
    new_status = status
    if et == "pickup_confirmed":
        new_status = "picked_up"
        await db.jobs.update_one({"id": job_id}, {"$set": {"status": "picked_up", "picked_up_at": doc["timestamp"]}})
    elif et == "in_transit_ping" and status == "picked_up":
        new_status = "in_transit"
        await db.jobs.update_one({"id": job_id}, {"$set": {"status": "in_transit"}})
    elif et == "delivered":
        driver_id = job.get("assigned_driver_id") or job.get("accepted_by") or current_user["id"]
        settlement = await settle_job_completion(job, driver_id, "delivered")
        new_status = "delivered"
    elif et == "returned":
        new_status = "returned"
        await db.jobs.update_one({"id": job_id}, {"$set": {"status": "returned"}})
        await notify_job_return(job)

    return {**doc, "job_status": new_status, "settlement": settlement}

# ---- Delivery evidence (signature / ID capture) ----
EVIDENCE_KINDS = {"signature", "id_photo"}

@api_router.post("/jobs/{job_id}/delivery-evidence", status_code=201)
async def upload_delivery_evidence(job_id: str, file: UploadFile = File(...), kind: str = Form("signature"), current_user: dict = Depends(get_current_user)):
    if kind not in EVIDENCE_KINDS:
        raise HTTPException(status_code=422, detail="kind must be 'signature' or 'id_photo'")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    role = current_user.get("role")
    if role == "driver" and current_user["id"] not in (job.get("accepted_by"), job.get("assigned_driver_id")):
        raise HTTPException(status_code=403, detail="Only the assigned driver can upload delivery evidence")
    if role == "facility":
        raise HTTPException(status_code=403, detail="Not authorized")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=422, detail="Only JPG, PNG, WEBP, HEIC or PDF files are accepted")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    path = f"{STORAGE_APP_PREFIX}/delivery-evidence/{job_id}/{kind}-{uuid.uuid4()}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, content_type)
    except Exception as e:
        logging.getLogger(__name__).error(f"Evidence upload failed: {e}")
        raise HTTPException(status_code=502, detail="Evidence storage is temporarily unavailable. Please try again.")
    evidence_id = str(uuid.uuid4())
    await db.delivery_evidence.insert_one({
        "id": evidence_id,
        "job_id": job_id,
        "kind": kind,
        "storage_path": result["path"],
        "content_type": content_type,
        "size": len(data),
        "uploaded_by": current_user["id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    })
    await log_audit(current_user, "upload", "delivery_evidence", evidence_id)
    return {"evidence_id": evidence_id, "evidence_url": f"/api/delivery-evidence/{evidence_id}/file", "kind": kind}

@api_router.get("/delivery-evidence/{evidence_id}/file")
async def serve_delivery_evidence(evidence_id: str, request: Request, auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    ev = await db.delivery_evidence.find_one({"id": evidence_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    job = await db.jobs.find_one({"id": ev["job_id"]}, {"_id": 0})
    if job:
        await assert_job_access(job, current_user)
    elif current_user.get("role") not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        data, ct = await asyncio.to_thread(get_object, ev["storage_path"])
    except Exception as e:
        logging.getLogger(__name__).error(f"Evidence fetch failed: {e}")
        raise HTTPException(status_code=502, detail="Evidence storage is temporarily unavailable")
    await log_audit(current_user, "view", "delivery_evidence", evidence_id)
    return Response(content=data, media_type=ev.get("content_type") or ct)

# ---- Notifications ----
async def notify_users(user_ids, type_: str, job_id: str, message: str):
    now = datetime.now(timezone.utc).isoformat()
    docs = [{
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "type": type_,
        "job_id": job_id,
        "message": message,
        "read": False,
        "created_at": now
    } for uid in {u for u in user_ids if u}]
    if docs:
        await db.notifications.insert_many(docs)

async def notify_job_return(job: dict):
    targets = [job.get("posted_by")]
    if job.get("facility_id"):
        fac = await db.facilities.find_one({"id": job["facility_id"]}, {"_id": 0, "owner_user_id": 1})
        if fac:
            targets.append(fac.get("owner_user_id"))
    dispatchers = await db.users.find({"role": "dispatcher"}, {"_id": 0, "id": 1}).to_list(100)
    targets += [d["id"] for d in dispatchers]
    await notify_users(targets, "job_returned", job["id"],
                       "Delivery could not be completed — the driver is returning the item to the pickup facility.")

@api_router.get("/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    notes = await db.notifications.find({"user_id": current_user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"notifications": notes, "unread": sum(1 for n in notes if not n.get("read"))}

@api_router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.notifications.update_one({"id": notification_id, "user_id": current_user["id"]}, {"$set": {"read": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}

@api_router.get("/jobs/{job_id}/custody-events")
async def list_custody_events(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await assert_job_access(job, current_user)
    await log_view_once(current_user, "job_custody", job_id)
    events = await db.custody_events.find({"job_id": job_id}, {"_id": 0}).sort("timestamp", 1).to_list(1000)
    return {"custody_events": events, "count": len(events)}

@api_router.get("/custody-events/{event_id}")
async def get_custody_event(event_id: str, current_user: dict = Depends(get_current_user)):
    event = await db.custody_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Custody event not found")
    job = await db.jobs.find_one({"id": event["job_id"]}, {"_id": 0})
    if job:
        await assert_job_access(job, current_user)
    elif current_user.get("role") not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    return event

@api_router.put("/custody-events/{event_id}")
@api_router.patch("/custody-events/{event_id}")
async def update_custody_event(event_id: str, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=405, detail="Custody events are append-only and cannot be modified")

@api_router.delete("/custody-events/{event_id}")
async def delete_custody_event(event_id: str, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=405, detail="Custody events are append-only and cannot be deleted")

# ---- Audit logs (compliance) ----
@api_router.get("/audit-logs")
async def get_audit_logs(
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    staff: dict = Depends(require_staff)
):
    query = {}
    if entity:
        query["entity"] = entity
    if entity_id:
        query["entity_id"] = entity_id
    if actor_id:
        query["actor_id"] = actor_id
    if action:
        query["action"] = action
    ts = {}
    if date_from:
        ts["$gte"] = date_from
    if date_to:
        ts["$lte"] = date_to + ("T23:59:59.999999+00:00" if len(date_to) == 10 else "")
    if ts:
        query["timestamp"] = ts
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        matched_users = await db.users.find(
            {"$or": [{"email": rx}, {"full_name": rx}]}, {"_id": 0, "id": 1}).to_list(200)
        actor_ids = [u["id"] for u in matched_users]
        query.setdefault("$and", []).append(
            {"$or": [{"action": rx}, {"entity": rx}, {"entity_id": rx}, {"actor_id": {"$in": actor_ids}}]})
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 1000))
    uids = list({l["actor_id"] for l in logs})
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    for l in logs:
        u = users.get(l["actor_id"])
        l["actor_name"] = u.get("full_name") if u else None
        l["actor_email"] = u.get("email") if u else None
    return {"logs": logs, "count": len(logs)}

# ---- Driver Onboarding (documents + verification) ----
def build_checklist(docs_by_type: dict, rec: dict):
    checklist = []
    for dt, meta in DRIVER_DOC_TYPES.items():
        doc = docs_by_type.get(dt)
        checklist.append({
            "doc_type": dt,
            "label": meta["label"],
            "required": meta["required"],
            "needs_expiry": meta.get("needs_expiry", False),
            "unlocks": meta.get("unlocks"),
            "status": doc["status"] if doc else "missing",
            "doc_id": doc["id"] if doc else None,
            "original_filename": doc.get("original_filename") if doc else None,
            "uploaded_at": doc.get("uploaded_at") if doc else None,
            "insurance_expiry": doc.get("insurance_expiry") if doc else None,
            "review_notes": doc.get("review_notes") if doc else None,
        })
    required_submitted = all(
        docs_by_type.get(dt) and docs_by_type[dt]["status"] != "rejected"
        for dt, meta in DRIVER_DOC_TYPES.items() if meta["required"]
    )
    return checklist, required_submitted

@api_router.get("/driver/onboarding")
async def get_driver_onboarding(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Driver access required")
    rec = await ensure_driver_record(current_user["id"])
    docs = await db.driver_documents.find({"user_id": current_user["id"], "is_deleted": False}, {"_id": 0}).to_list(50)
    docs_by_type = {d["doc_type"]: d for d in docs}
    checklist, required_submitted = build_checklist(docs_by_type, rec)
    return {
        "verification_status": rec.get("verification_status", "incomplete"),
        "checklist": checklist,
        "all_required_submitted": required_submitted,
        "cold_chain_certified": rec.get("cold_chain_certified", False)
    }

@api_router.post("/driver/documents/{doc_type}", status_code=201)
async def upload_driver_document(
    doc_type: str,
    file: UploadFile = File(...),
    insurance_expiry: Optional[str] = Form(None),
    vehicle_plate: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Driver access required")
    if doc_type not in DRIVER_DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid doc_type. Allowed: {sorted(DRIVER_DOC_TYPES)}")
    if doc_type == "commercial_insurance" and not insurance_expiry:
        raise HTTPException(status_code=422, detail="insurance_expiry is required for commercial insurance")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=422, detail="Only JPG, PNG, WEBP, HEIC or PDF files are accepted")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")

    rec = await ensure_driver_record(current_user["id"])
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    path = f"{STORAGE_APP_PREFIX}/driver-docs/{current_user['id']}/{doc_type}/{uuid.uuid4()}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, content_type)
    except Exception as e:
        logging.getLogger(__name__).error(f"Document upload to storage failed: {e}")
        raise HTTPException(status_code=502, detail="Document storage is temporarily unavailable. Please try again.")

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.driver_documents.find_one({"user_id": current_user["id"], "doc_type": doc_type, "is_deleted": False}, {"_id": 0})
    doc_fields = {
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": len(data),
        "insurance_expiry": insurance_expiry,
        "status": "pending",
        "uploaded_at": now,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_notes": None,
    }
    if existing:
        doc_id = existing["id"]
        await db.driver_documents.update_one({"id": doc_id}, {"$set": doc_fields})
    else:
        doc_id = str(uuid.uuid4())
        await db.driver_documents.insert_one({"id": doc_id, "user_id": current_user["id"], "doc_type": doc_type, "is_deleted": False, **doc_fields})

    driver_updates = {}
    if doc_type in DOC_TO_DRIVER_FIELD:
        driver_updates[DOC_TO_DRIVER_FIELD[doc_type]] = "pending"
    if insurance_expiry and doc_type == "commercial_insurance":
        driver_updates["insurance_expiry"] = insurance_expiry
    if vehicle_plate and doc_type == "vehicle_registration":
        driver_updates["vehicle_plate"] = vehicle_plate
    if driver_updates:
        await db.drivers.update_one({"user_id": current_user["id"]}, {"$set": driver_updates})

    docs = await db.driver_documents.find({"user_id": current_user["id"], "is_deleted": False}, {"_id": 0}).to_list(50)
    _, required_submitted = build_checklist({d["doc_type"]: d for d in docs}, rec)
    if required_submitted and rec.get("verification_status") in ("incomplete", "rejected"):
        await db.drivers.update_one({"user_id": current_user["id"]}, {"$set": {"verification_status": "pending_review"}})

    await log_audit(current_user, "upload", "driver_document", doc_id)
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "status": "pending",
        "all_required_submitted": required_submitted
    }

@api_router.get("/driver-documents/{doc_id}/file")
async def serve_driver_document(doc_id: str, request: Request, auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    doc = await db.driver_documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["user_id"] != current_user["id"] and current_user.get("role") not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        data, ct = await asyncio.to_thread(get_object, doc["storage_path"])
    except Exception as e:
        logging.getLogger(__name__).error(f"Document fetch failed: {e}")
        raise HTTPException(status_code=502, detail="Document storage is temporarily unavailable")
    await log_audit(current_user, "view", "driver_document", doc_id)
    return Response(content=data, media_type=doc.get("content_type") or ct)

# ---- Staff review of driver verifications ----
class DocumentReview(BaseModel):
    status: str
    review_notes: Optional[str] = None

class VerificationUpdate(BaseModel):
    verification_status: str

@api_router.get("/admin/driver-verifications")
async def list_driver_verifications(staff: dict = Depends(require_staff)):
    records = await db.drivers.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    user_ids = [r["user_id"] for r in records]
    users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    users_by_id = {u["id"]: u for u in users}
    docs = await db.driver_documents.find({"user_id": {"$in": user_ids}, "is_deleted": False}, {"_id": 0}).to_list(2000)
    docs_by_user = {}
    for d in docs:
        docs_by_user.setdefault(d["user_id"], {})[d["doc_type"]] = d
    rating_pipeline = [
        {"$match": {"driver_id": {"$in": user_ids}, "hidden": {"$ne": True}}},
        {"$group": {"_id": "$driver_id", "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    ratings = {r["_id"]: r async for r in db.reviews.aggregate(rating_pipeline)}
    out = []
    for rec in records:
        u = users_by_id.get(rec["user_id"])
        if not u:
            continue
        checklist, required_submitted = build_checklist(docs_by_user.get(rec["user_id"], {}), rec)
        rating = ratings.get(rec["user_id"])
        issues = driver_compliance_issues(rec)
        out.append({
            "user_id": rec["user_id"],
            "full_name": u.get("full_name"),
            "email": u.get("email"),
            "phone": u.get("phone"),
            "verification_status": rec.get("verification_status", "incomplete"),
            "cold_chain_certified": rec.get("cold_chain_certified", False),
            "vehicle_plate": rec.get("vehicle_plate"),
            "cvor_status": rec.get("cvor_status", "not_submitted"),
            "tdg_cert_status": rec.get("tdg_cert_status", "not_submitted"),
            "vulnerable_sector_check_status": rec.get("vulnerable_sector_check_status", "not_submitted"),
            "insurance_status": rec.get("insurance_status", "not_submitted"),
            "insurance_expiry": rec.get("insurance_expiry"),
            "insurance_flag": insurance_flag_of(rec.get("insurance_expiry")),
            "rating_avg": round(rating["avg"], 2) if rating else rec.get("rating_avg", 0.0),
            "rating_count": rating["count"] if rating else 0,
            "total_trips": rec.get("total_trips", 0),
            "compliant": not issues,
            "compliance_issues": issues,
            "all_required_submitted": required_submitted,
            "checklist": checklist
        })
    return {"drivers": out}

@api_router.put("/admin/driver-documents/{doc_id}")
async def review_driver_document(doc_id: str, payload: DocumentReview, staff: dict = Depends(require_staff)):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    doc = await db.driver_documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.driver_documents.update_one({"id": doc_id}, {"$set": {
        "status": payload.status,
        "review_notes": payload.review_notes,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": staff["id"]
    }})
    driver_updates = {}
    if doc["doc_type"] in DOC_TO_DRIVER_FIELD:
        driver_updates[DOC_TO_DRIVER_FIELD[doc["doc_type"]]] = "valid" if payload.status == "approved" else "rejected"
    if doc["doc_type"] == "cold_chain_cert":
        driver_updates["cold_chain_certified"] = payload.status == "approved"
    if driver_updates:
        await db.drivers.update_one({"user_id": doc["user_id"]}, {"$set": driver_updates})
    await log_audit(staff, "review", "driver_document", doc_id)
    updated = await db.driver_documents.find_one({"id": doc_id}, {"_id": 0})
    return updated

@api_router.put("/admin/driver-verifications/{user_id}")
async def update_driver_verification(user_id: str, payload: VerificationUpdate, staff: dict = Depends(require_staff)):
    validate_enum(payload.verification_status, DRIVER_VERIFICATION_STATUSES, "verification_status")
    rec = await db.drivers.find_one({"user_id": user_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Driver record not found")
    if payload.verification_status == "approved" and rec.get("verification_status") != "suspended":
        docs = await db.driver_documents.find({"user_id": user_id, "is_deleted": False}, {"_id": 0}).to_list(50)
        docs_by_type = {d["doc_type"]: d for d in docs}
        blockers = [
            meta["label"] for dt, meta in DRIVER_DOC_TYPES.items()
            if meta["required"] and (dt not in docs_by_type or docs_by_type[dt]["status"] == "rejected")
        ]
        if blockers:
            raise HTTPException(status_code=400, detail=f"Cannot approve driver — missing or rejected required documents: {', '.join(blockers)}")
    result = await db.drivers.update_one({"user_id": user_id}, {"$set": {"verification_status": payload.verification_status}})
    await log_audit(staff, "update", "driver_verification", user_id,
                    details={"from": rec.get("verification_status"), "to": payload.verification_status})
    rec = await db.drivers.find_one({"user_id": user_id}, {"_id": 0})
    return rec

# ---- Facility transport requests ----
class FacilityRequestCreate(BaseModel):
    pickup_address: Optional[str] = None
    recipient_name: str
    dropoff_address: str
    recipient_phone: str
    item_count: int = Field(ge=1, le=100)
    item_category: str
    handling_flags: List[str] = []
    special_instructions: Optional[str] = None  # non-clinical handling notes only
    requested_pickup_time: str
    facility_id: Optional[str] = None

CATEGORY_TITLES = {
    "prescription": "Prescription delivery", "lab_sample": "Lab sample transport",
    "biological": "Biological transport", "medical_equipment": "Medical equipment delivery",
    "medical_supply": "Medical supply delivery", "other": "Medical transport"
}

def _geocode(addr: str):
    def q(query):
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "ca"},
            headers={"User-Agent": "MediTransOntario/1.0"}, timeout=8
        )
        d = r.json()
        return (float(d[0]["lat"]), float(d[0]["lon"])) if d else None
    result = q(addr)
    if not result:
        # retry without the house number (area-level match)
        parts = [p.strip() for p in addr.split(",")]
        parts[0] = re.sub(r"^[\d\-#]+[A-Za-z]?\s+", "", parts[0]).strip() or parts[0]
        result = q(", ".join(parts))
    return result

def _haversine_km(a, b):
    import math
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

async def estimate_distance_km(pickup: str, dropoff: str) -> Optional[float]:
    try:
        p1 = await asyncio.to_thread(_geocode, pickup)
        p2 = await asyncio.to_thread(_geocode, dropoff)
        if p1 and p2:
            return round(_haversine_km(p1, p2) * 1.3, 1)  # road-distance factor
    except Exception as e:
        logging.getLogger(__name__).warning(f"Distance estimate failed: {e}")
    return None

def _city_of(addr: str) -> str:
    parts = [p.strip() for p in (addr or "").split(",")]
    return parts[1] if len(parts) > 1 else ""

@api_router.post("/facility/requests", status_code=201)
async def create_facility_request(payload: FacilityRequestCreate, current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role not in ("facility", "admin", "dispatcher"):
        raise HTTPException(status_code=403, detail="Facility access required")
    validate_enum(payload.item_category, ITEM_CATEGORIES, "item_category")
    validate_handling_flags(payload.handling_flags)
    if payload.facility_id:
        facility = await db.facilities.find_one({"id": payload.facility_id}, {"_id": 0})
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")
        if role == "facility" and facility.get("owner_user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not your facility")
    else:
        facility = await db.facilities.find_one({"owner_user_id": current_user["id"]}, {"_id": 0})
        if not facility:
            raise HTTPException(status_code=400, detail="Set up your facility profile before booking transport")
    if facility.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="This facility is suspended and cannot book new transports. Contact the administrator.")

    pickup = payload.pickup_address or facility.get("address")
    distance = await estimate_distance_km(pickup, payload.dropoff_address)
    fees = await get_fees_from_db()
    billed_km = distance if distance is not None else 10.0
    if facility.get("per_delivery_rate") is not None:
        payout = float(facility["per_delivery_rate"])
    else:
        payout = max(float(fees.get("minimum_fee", 25.0)), float(fees.get("base_rate_per_km", 1.5)) * billed_km)
    if "urgent" in payload.handling_flags:
        payout *= float(fees.get("urgent_multiplier", 1.5))
    if "cold_chain" in payload.handling_flags:
        payout += float(fees.get("temperature_controlled_fee", 15.0))
    payout = round(payout, 2)

    now = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        "title": CATEGORY_TITLES.get(payload.item_category, "Medical transport"),
        "pickup_address": pickup,
        "delivery_address": payload.dropoff_address,
        "dropoff_address": payload.dropoff_address,
        "pickup_city": _city_of(pickup),
        "delivery_city": _city_of(payload.dropoff_address),
        "goods_type": None,
        "temperature_controlled": "cold_chain" in payload.handling_flags,
        "urgency": "urgent" if "urgent" in payload.handling_flags else "standard",
        "estimated_distance_km": billed_km,
        "distance_km": billed_km,
        "offered_price": payout,
        "payout_amount": payout,
        "notes": None,
        "facility_id": facility["id"],
        "item_category": payload.item_category,
        "handling_flags": payload.handling_flags,
        "special_instructions": payload.special_instructions,
        "item_count": payload.item_count,
        "recipient_name": payload.recipient_name,
        "recipient_phone": payload.recipient_phone,
        "requested_pickup_time": payload.requested_pickup_time,
        "distance_estimated": distance is not None,
        "status": "offered",
        "posted_by": current_user["id"],
        "accepted_by": None,
        "assigned_driver_id": None,
        "created_at": now,
        "accepted_at": None,
        "completed_at": None,
        "picked_up_at": None,
        "delivered_at": None
    }
    await db.jobs.insert_one(job_doc)
    await log_audit(current_user, "create", "job", job_id)
    await log_audit(current_user, "update", "job", job_id)  # created -> offered
    job_doc.pop("_id", None)
    return job_doc

@api_router.get("/facility/deliveries")
async def facility_deliveries(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    if role not in ("facility", "admin", "dispatcher"):
        raise HTTPException(status_code=403, detail="Facility access required")
    if role == "facility":
        fac_ids = await facility_ids_owned_by(current_user["id"])
        query = {"$or": [{"posted_by": current_user["id"]}, {"facility_id": {"$in": fac_ids}}]}
    else:
        query = {}
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    driver_ids = list({j.get("assigned_driver_id") or j.get("accepted_by") for j in jobs if j.get("assigned_driver_id") or j.get("accepted_by")})
    users = await db.users.find({"id": {"$in": driver_ids}}, {"_id": 0, "id": 1, "full_name": 1}).to_list(200)
    names = {u["id"]: u["full_name"] for u in users}
    ratings = {}
    for did in driver_ids:
        ratings[did] = await _compute_driver_rating(did)
    out = []
    for j in jobs:
        did = j.get("assigned_driver_id") or j.get("accepted_by")
        last_ev = await db.custody_events.find_one({"job_id": j["id"]}, {"_id": 0}, sort=[("timestamp", -1)])
        out.append({
            **j,
            "driver": ({"name": names.get(did) or "Driver (deactivated)", "rating_avg": ratings.get(did, {}).get("avg", 0), "rating_count": ratings.get(did, {}).get("count", 0)} if did else None),
            "last_event": last_ev
        })
    return {"deliveries": out}

# ---- Facility billing (facility-fee side; separate from driver commission) ----
HST_RATE = 0.13

async def _facility_statement(user: dict, month: str):
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    role = user.get("role")
    if role not in ("facility", "admin", "dispatcher"):
        raise HTTPException(status_code=403, detail="Facility access required")
    if role == "facility":
        fac_ids = await facility_ids_owned_by(user["id"])
        query = {"$or": [{"posted_by": user["id"]}, {"facility_id": {"$in": fac_ids}}]}
        facility = await db.facilities.find_one({"owner_user_id": user["id"]}, {"_id": 0})
    else:
        query = {}
        facility = None
    query = {"$and": [query, {"status": {"$in": ["delivered", "completed"]}}]} if query else {"status": {"$in": ["delivered", "completed"]}}
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    items = []
    for j in jobs:
        done_at = j.get("delivered_at") or j.get("completed_at") or ""
        if not done_at.startswith(month):
            continue
        items.append({
            "job_id": j["id"],
            "date": done_at,
            "title": j.get("title") or "Medical transport",
            "recipient_name": j.get("recipient_name"),
            "dropoff_address": j.get("delivery_address"),
            "amount": round(float(j.get("payout_amount") or j.get("offered_price") or 0), 2)
        })
    items.sort(key=lambda i: i["date"])
    subtotal = round(sum(i["amount"] for i in items), 2)
    hst = round(subtotal * HST_RATE, 2)
    return {
        "month": month,
        "facility": {"name": facility.get("name"), "address": facility.get("address"), "billing_email": facility.get("billing_email")} if facility else None,
        "items": items,
        "subtotal": subtotal,
        "hst_rate": HST_RATE,
        "hst": hst,
        "total": round(subtotal + hst, 2),
        "currency": "CAD"
    }

@api_router.get("/facility/billing")
async def facility_billing(month: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    return await _facility_statement(current_user, month)

@api_router.get("/facility/billing/export")
async def facility_billing_export(request: Request, month: Optional[str] = None, format: str = "csv", auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    st = await _facility_statement(current_user, month)
    fname = f"meditrans-statement-{month}"
    if format == "csv":
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["MediTrans Ontario — Facility Statement", st["month"]])
        if st["facility"]:
            w.writerow([st["facility"]["name"], st["facility"]["address"], st["facility"]["billing_email"]])
        w.writerow([])
        w.writerow(["Date", "Delivery", "Recipient", "Dropoff", "Amount (CAD)"])
        for i in st["items"]:
            w.writerow([i["date"][:16].replace("T", " "), i["title"], i["recipient_name"] or "", i["dropoff_address"] or "", f"{i['amount']:.2f}"])
        w.writerow([])
        w.writerow(["", "", "", "Subtotal", f"{st['subtotal']:.2f}"])
        w.writerow(["", "", "", "HST (13%)", f"{st['hst']:.2f}"])
        w.writerow(["", "", "", "Total", f"{st['total']:.2f}"])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fname}.csv"})
    elif format == "pdf":
        def build_pdf():
            import io
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.7 * inch)
            styles = getSampleStyleSheet()
            story = [
                Paragraph("MediTrans Ontario — Facility Statement", styles["Title"]),
                Paragraph(f"Statement month: {st['month']}", styles["Normal"]),
            ]
            if st["facility"]:
                story.append(Paragraph(f"{st['facility']['name']} · {st['facility']['address']} · {st['facility']['billing_email']}", styles["Normal"]))
            story.append(Spacer(1, 14))
            data = [["Date", "Delivery", "Recipient", "Amount (CAD)"]]
            for i in st["items"]:
                data.append([i["date"][:16].replace("T", " "), i["title"], i["recipient_name"] or "", f"${i['amount']:.2f}"])
            data += [["", "", "Subtotal", f"${st['subtotal']:.2f}"],
                     ["", "", "HST (13%)", f"${st['hst']:.2f}"],
                     ["", "", "Total", f"${st['total']:.2f}"]]
            t = Table(data, colWidths=[1.5 * inch, 2.4 * inch, 1.8 * inch, 1.3 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -4), 0.4, colors.HexColor("#cbd5e1")),
                ("LINEABOVE", (2, -3), (-1, -3), 0.8, colors.HexColor("#1e3a8a")),
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
            ]))
            story.append(t)
            doc.build(story)
            return buf.getvalue()
        pdf_bytes = await asyncio.to_thread(build_pdf)
        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename={fname}.pdf"})
    raise HTTPException(status_code=422, detail="format must be csv or pdf")

# ---- Admin: Facility Management ----
@api_router.get("/admin/facilities")
async def admin_list_facilities(staff: dict = Depends(require_staff)):
    facilities = await db.facilities.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    fac_ids = [f["id"] for f in facilities]
    owner_ids = list({f.get("owner_user_id") for f in facilities if f.get("owner_user_id")})
    owners = {u["id"]: u async for u in db.users.find({"id": {"$in": owner_ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "phone": 1})}
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"facility_id": {"$in": fac_ids}}},
        {"$group": {
            "_id": "$facility_id",
            "total_jobs": {"$sum": 1},
            "delivered_jobs": {"$sum": {"$cond": [{"$in": ["$status", ["delivered", "completed"]]}, 1, 0]}},
            "last_30d_jobs": {"$sum": {"$cond": [{"$gte": ["$created_at", cutoff_30d]}, 1, 0]}},
            "total_billed": {"$sum": {"$cond": [
                {"$in": ["$status", ["delivered", "completed"]]},
                {"$ifNull": ["$payout_amount", {"$ifNull": ["$offered_price", 0]}]}, 0]}}
        }}
    ]
    volumes = {v["_id"]: v async for v in db.jobs.aggregate(pipeline)}
    out = []
    for f in facilities:
        v = volumes.get(f["id"], {})
        owner = owners.get(f.get("owner_user_id"))
        out.append({
            **f,
            "owner": {"full_name": owner.get("full_name"), "email": owner.get("email"), "phone": owner.get("phone")} if owner else None,
            "volume": {
                "total_jobs": v.get("total_jobs", 0),
                "delivered_jobs": v.get("delivered_jobs", 0),
                "last_30d_jobs": v.get("last_30d_jobs", 0),
                "total_billed": round(v.get("total_billed", 0), 2)
            }
        })
    return {"facilities": out}

# ---- Admin: Billing / Commission Engine ----
async def _month_financials(month: str):
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    y, m = int(month[:4]), int(month[5:7])
    next_month = f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"
    done_range = {"$gte": f"{month}-01", "$lt": f"{next_month}-01"}
    jobs = await db.jobs.find({
        "status": {"$in": ["delivered", "completed"]},
        "$or": [{"delivered_at": done_range}, {"delivered_at": None, "completed_at": done_range}]
    }, {"_id": 0}).to_list(20000)
    job_ids = [j["id"] for j in jobs]
    commissions = {e["job_id"]: e async for e in db.ledger.find(
        {"type": "commission", "job_id": {"$in": job_ids}}, {"_id": 0})}
    cancel_fees = await db.ledger.find(
        {"type": "cancellation_fee", "created_at": done_range}, {"_id": 0}).to_list(5000)
    fac_ids = list({j["facility_id"] for j in jobs if j.get("facility_id")})
    facilities = {f["id"]: f async for f in db.facilities.find({"id": {"$in": fac_ids}}, {"_id": 0})}
    driver_ids = list({j.get("accepted_by") or j.get("assigned_driver_id") for j in jobs if j.get("accepted_by") or j.get("assigned_driver_id")})
    driver_ids += [e["driver_id"] for e in cancel_fees if e.get("driver_id")]
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": list(set(driver_ids))}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    lines = []
    for j in jobs:
        gross = round(float(j.get("offered_price") or j.get("payout_amount") or 0), 2)
        entry = commissions.get(j["id"])
        commission = round(float(entry["amount"]), 2) if entry else round(gross * 0.20, 2)
        did = j.get("accepted_by") or j.get("assigned_driver_id")
        driver = users.get(did)
        facility = facilities.get(j.get("facility_id"))
        lines.append({
            "job_id": j["id"],
            "date": j.get("delivered_at") or j.get("completed_at"),
            "title": j.get("title") or "Medical transport",
            "facility_id": j.get("facility_id"),
            "facility_name": facility.get("name") if facility else "Direct booking",
            "driver_id": did,
            "driver_name": driver.get("full_name") if driver else None,
            "region": j.get("delivery_city") or j.get("pickup_city") or "Unknown",
            "facility_charge": gross,
            "driver_gross": gross,
            "commission": commission,
            "commission_rate": round(commission / gross, 4) if gross else 0.20,
            "driver_net": round(gross - commission, 2)
        })
    return lines, cancel_fees, facilities, users

@api_router.get("/admin/billing/summary")
async def admin_billing_summary(month: Optional[str] = None, admin: dict = Depends(require_admin)):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    lines, cancel_fees, facilities, users = await _month_financials(month)
    gross = round(sum(l["facility_charge"] for l in lines), 2)
    commission = round(sum(l["commission"] for l in lines), 2)
    fees_total = round(sum(float(e.get("amount", 0)) for e in cancel_fees), 2)
    by_facility, by_region = {}, {}
    for l in lines:
        f = by_facility.setdefault(l["facility_id"] or "direct", {"facility_id": l["facility_id"], "name": l["facility_name"], "trips": 0, "gross": 0, "commission": 0})
        f["trips"] += 1; f["gross"] += l["facility_charge"]; f["commission"] += l["commission"]
        r = by_region.setdefault(l["region"], {"region": l["region"], "trips": 0, "gross": 0, "commission": 0})
        r["trips"] += 1; r["gross"] += l["facility_charge"]; r["commission"] += l["commission"]
    for coll in (by_facility, by_region):
        for v in coll.values():
            v["gross"] = round(v["gross"], 2); v["commission"] = round(v["commission"], 2)
    return {
        "month": month,
        "kpis": {
            "completed_trips": len(lines),
            "gross_delivery_value": gross,
            "commission_earned": commission,
            "cancellation_fees": fees_total,
            "platform_revenue": round(commission + fees_total, 2)
        },
        "by_facility": sorted(by_facility.values(), key=lambda x: -x["gross"]),
        "by_region": sorted(by_region.values(), key=lambda x: -x["gross"]),
        "currency": "CAD"
    }

@api_router.get("/admin/billing/invoices")
async def admin_billing_invoices(month: Optional[str] = None, admin: dict = Depends(require_admin)):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    lines, _, facilities, _ = await _month_financials(month)
    grouped = {}
    for l in lines:
        g = grouped.setdefault(l["facility_id"] or "direct", {"lines": [], "facility_id": l["facility_id"], "name": l["facility_name"]})
        g["lines"].append(l)
    invoices = []
    for g in grouped.values():
        fac = facilities.get(g["facility_id"]) or {}
        subtotal = round(sum(l["facility_charge"] for l in g["lines"]), 2)
        hst = round(subtotal * HST_RATE, 2)
        invoices.append({
            "facility_id": g["facility_id"],
            "facility_name": g["name"],
            "billing_email": fac.get("billing_email"),
            "deliveries": len(g["lines"]),
            "subtotal": subtotal,
            "hst": hst,
            "total": round(subtotal + hst, 2),
            "commission_earned": round(sum(l["commission"] for l in g["lines"]), 2),
            "items": sorted(g["lines"], key=lambda l: l["date"] or "")
        })
    invoices.sort(key=lambda i: -i["subtotal"])
    return {"month": month, "invoices": invoices, "hst_rate": HST_RATE, "currency": "CAD"}

@api_router.get("/admin/billing/driver-statements")
async def admin_billing_driver_statements(month: Optional[str] = None, admin: dict = Depends(require_admin)):
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    lines, cancel_fees, _, users = await _month_financials(month)
    grouped = {}
    for l in lines:
        if not l["driver_id"]:
            continue
        g = grouped.setdefault(l["driver_id"], {"lines": [], "fees": []})
        g["lines"].append(l)
    for e in cancel_fees:
        if e.get("driver_id"):
            grouped.setdefault(e["driver_id"], {"lines": [], "fees": []})["fees"].append(e)
    statements = []
    for did, g in grouped.items():
        u = users.get(did) or {}
        gross = round(sum(l["driver_gross"] for l in g["lines"]), 2)
        commission = round(sum(l["commission"] for l in g["lines"]), 2)
        fees_total = round(sum(float(e.get("amount", 0)) for e in g["fees"]), 2)
        statements.append({
            "driver_id": did,
            "driver_name": u.get("full_name") or "Unknown driver",
            "email": u.get("email"),
            "trips": len(g["lines"]),
            "gross": gross,
            "commission": commission,
            "cancellation_fees": fees_total,
            "net_payable": round(gross - commission - fees_total, 2),
            "items": sorted(g["lines"], key=lambda l: l["date"] or ""),
            "fee_items": g["fees"]
        })
    statements.sort(key=lambda s: -s["gross"])
    return {"month": month, "statements": statements, "currency": "CAD"}

@api_router.get("/admin/billing/export")
async def admin_billing_export(request: Request, month: Optional[str] = None, report: str = "revenue", auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if report not in ("revenue", "invoices", "driver_statements", "jobs"):
        raise HTTPException(status_code=422, detail="report must be one of: revenue, invoices, driver_statements, jobs")
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    if report == "invoices":
        data = await admin_billing_invoices(month, current_user)
        w.writerow(["MediTrans Ontario — Facility Invoices", month])
        w.writerow(["Facility", "Billing Email", "Deliveries", "Subtotal (CAD)", "HST 13% (CAD)", "Invoice Total (CAD)", "Commission Earned (CAD)"])
        for i in data["invoices"]:
            w.writerow([i["facility_name"], i["billing_email"] or "", i["deliveries"], f"{i['subtotal']:.2f}", f"{i['hst']:.2f}", f"{i['total']:.2f}", f"{i['commission_earned']:.2f}"])
    elif report == "driver_statements":
        data = await admin_billing_driver_statements(month, current_user)
        w.writerow(["MediTrans Ontario — Driver Earnings Statements", month])
        w.writerow(["Driver", "Email", "Trips", "Gross (CAD)", "Commission (CAD)", "Cancellation Fees (CAD)", "Net Payable (CAD)"])
        for s in data["statements"]:
            w.writerow([s["driver_name"], s["email"] or "", s["trips"], f"{s['gross']:.2f}", f"{s['commission']:.2f}", f"{s['cancellation_fees']:.2f}", f"{s['net_payable']:.2f}"])
    elif report == "jobs":
        lines, _, _, _ = await _month_financials(month)
        w.writerow(["MediTrans Ontario — Per-Job Breakdown", month])
        w.writerow(["Date", "Job ID", "Delivery", "Facility", "Driver", "Region", "Facility Charge (CAD)", "Commission Rate", "Commission (CAD)", "Driver Net (CAD)"])
        for l in sorted(lines, key=lambda x: x["date"] or ""):
            w.writerow([(l["date"] or "")[:16].replace("T", " "), l["job_id"], l["title"], l["facility_name"], l["driver_name"] or "", l["region"],
                        f"{l['facility_charge']:.2f}", f"{l['commission_rate']*100:.0f}%", f"{l['commission']:.2f}", f"{l['driver_net']:.2f}"])
    else:
        data = await admin_billing_summary(month, current_user)
        k = data["kpis"]
        w.writerow(["MediTrans Ontario — Platform Revenue Summary", month])
        w.writerow(["Completed Trips", "Gross Delivery Value (CAD)", "Commission Earned (CAD)", "Cancellation Fees (CAD)", "Platform Revenue (CAD)"])
        w.writerow([k["completed_trips"], f"{k['gross_delivery_value']:.2f}", f"{k['commission_earned']:.2f}", f"{k['cancellation_fees']:.2f}", f"{k['platform_revenue']:.2f}"])
        w.writerow([])
        w.writerow(["Revenue by Facility"])
        w.writerow(["Facility", "Trips", "Gross (CAD)", "Commission (CAD)"])
        for f in data["by_facility"]:
            w.writerow([f["name"], f["trips"], f"{f['gross']:.2f}", f"{f['commission']:.2f}"])
        w.writerow([])
        w.writerow(["Revenue by Region"])
        w.writerow(["Region", "Trips", "Gross (CAD)", "Commission (CAD)"])
        for r in data["by_region"]:
            w.writerow([r["region"], r["trips"], f"{r['gross']:.2f}", f"{r['commission']:.2f}"])
    fname = f"meditrans-{report}-{month}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

# ---- Admin: Compliance ----
DEFAULT_RETENTION_DAYS = 365
REDACTED = "[REDACTED]"

async def get_retention_days() -> int:
    doc = await db.settings.find_one({"key": "data_retention"}, {"_id": 0})
    return int(doc["value"]["retention_days"]) if doc and doc.get("value") else DEFAULT_RETENTION_DAYS

async def run_retention_purge(actor: Optional[dict] = None) -> dict:
    days = await get_retention_days()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    jobs = await db.jobs.find({
        "status": {"$in": ["delivered", "completed", "cancelled", "returned"]},
        "data_purged": {"$ne": True},
        "created_at": {"$lt": cutoff}
    }, {"_id": 0, "id": 1}).to_list(20000)
    job_ids = [j["id"] for j in jobs]
    now = datetime.now(timezone.utc).isoformat()
    if job_ids:
        await db.jobs.update_many({"id": {"$in": job_ids}}, {"$set": {
            "recipient_name": REDACTED, "recipient_phone": REDACTED,
            "data_purged": True, "purged_at": now
        }})
        await db.custody_events.update_many(
            {"job_id": {"$in": job_ids}},
            [{"$set": {
                "recipient_name": {"$cond": [{"$ifNull": ["$recipient_name", False]}, REDACTED, "$recipient_name"]},
                "recipient_relationship": {"$cond": [{"$ifNull": ["$recipient_relationship", False]}, REDACTED, "$recipient_relationship"]},
                "evidence_url": None
            }}]
        )
    result = {"purged_jobs": len(job_ids), "retention_days": days, "cutoff": cutoff, "ran_at": now}
    await db.settings.update_one({"key": "last_purge"}, {"$set": {"key": "last_purge", "value": result}}, upsert=True)
    if actor or job_ids:
        system_actor = actor or {"id": "system", "role": "system"}
        await log_audit(system_actor, "purge", "data_retention", "recipient_pii", details=result)
    return result

async def retention_purge_loop():
    while True:
        try:
            await run_retention_purge()
        except Exception as e:
            logging.getLogger(__name__).error(f"Retention purge failed: {e}")
        await asyncio.sleep(24 * 3600)

@api_router.get("/admin/compliance/retention")
async def get_retention_setting(admin: dict = Depends(require_admin)):
    last = await db.settings.find_one({"key": "last_purge"}, {"_id": 0})
    return {"retention_days": await get_retention_days(), "last_purge": last["value"] if last else None}

class RetentionUpdate(BaseModel):
    retention_days: int = Field(ge=30, le=3650)

@api_router.put("/admin/compliance/retention")
async def update_retention_setting(payload: RetentionUpdate, admin: dict = Depends(require_admin)):
    prev = await get_retention_days()
    await db.settings.update_one(
        {"key": "data_retention"},
        {"$set": {"key": "data_retention", "value": {"retention_days": payload.retention_days},
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    await log_audit(admin, "update", "data_retention", "setting", details={"from": prev, "to": payload.retention_days})
    return {"retention_days": payload.retention_days}

@api_router.post("/admin/compliance/purge")
async def manual_retention_purge(admin: dict = Depends(require_admin)):
    return await run_retention_purge(actor=admin)

@api_router.get("/admin/compliance/missing-pod")
async def compliance_missing_pod(staff: dict = Depends(require_staff)):
    jobs = await db.jobs.find({"status": {"$in": ["delivered", "completed"]}}, {"_id": 0}).to_list(10000)
    job_ids = [j["id"] for j in jobs]
    delivered_events = {}
    async for e in db.custody_events.find({"job_id": {"$in": job_ids}, "event_type": "delivered"}, {"_id": 0}):
        delivered_events[e["job_id"]] = e
    fac_ids = list({j.get("facility_id") for j in jobs if j.get("facility_id")})
    facilities = {f["id"]: f async for f in db.facilities.find({"id": {"$in": fac_ids}}, {"_id": 0, "id": 1, "name": 1})}
    duids = list({j.get("accepted_by") or j.get("assigned_driver_id") for j in jobs})
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": duids}}, {"_id": 0, "id": 1, "full_name": 1})}
    out = []
    for j in jobs:
        ev = delivered_events.get(j["id"])
        if ev and ev.get("evidence_url"):
            continue
        if ev and j.get("data_purged"):
            continue
        did = j.get("accepted_by") or j.get("assigned_driver_id")
        out.append({
            "job_id": j["id"],
            "title": j.get("title") or "Medical transport",
            "facility_name": facilities.get(j.get("facility_id"), {}).get("name") or "Direct booking",
            "driver_name": users.get(did, {}).get("full_name"),
            "delivered_at": j.get("delivered_at") or j.get("completed_at"),
            "issue": "no_delivered_event" if not ev else "no_signature_evidence"
        })
    out.sort(key=lambda x: x["delivered_at"] or "", reverse=True)
    return {"jobs": out, "count": len(out)}

@api_router.get("/admin/compliance/credential-alerts")
async def compliance_credential_alerts(staff: dict = Depends(require_staff)):
    recs = await db.drivers.find({}, {"_id": 0}).to_list(2000)
    uids = [r["user_id"] for r in recs]
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    alerts = []
    for r in recs:
        flag = insurance_flag_of(r.get("insurance_expiry"))
        status = r.get("verification_status", "incomplete")
        issues = []
        if flag == "expired":
            issues.append({"type": "insurance_expired", "detail": f"Insurance expired {r.get('insurance_expiry')}"})
        elif flag == "expiring_soon":
            issues.append({"type": "insurance_expiring", "detail": f"Insurance expires {r.get('insurance_expiry')}"})
        if status in ("suspended", "rejected") and r.get("total_trips", 0) > 0:
            issues.append({"type": f"verification_{status}", "detail": f"Active driver is {status}"})
        if issues:
            u = users.get(r["user_id"], {})
            alerts.append({
                "user_id": r["user_id"],
                "driver_name": u.get("full_name"),
                "email": u.get("email"),
                "verification_status": status,
                "insurance_expiry": r.get("insurance_expiry"),
                "issues": issues
            })
    return {"alerts": alerts, "count": len(alerts)}

@api_router.get("/jobs/{job_id}/custody-record/pdf")
async def custody_record_pdf(job_id: str, request: Request, auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    if current_user.get("role") not in ("admin", "dispatcher"):
        raise HTTPException(status_code=403, detail="Staff access required")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    events = await db.custody_events.find({"job_id": job_id}, {"_id": 0}).sort("timestamp", 1).to_list(1000)
    audits = await db.audit_logs.find({"entity_id": job_id}, {"_id": 0}).sort("timestamp", 1).to_list(1000)
    uids = list({e.get("actor_id") for e in events if e.get("actor_id")} | {a["actor_id"] for a in audits})
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": uids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    facility = await db.facilities.find_one({"id": job.get("facility_id")}, {"_id": 0}) if job.get("facility_id") else None
    await log_audit(current_user, "export", "job_custody_record", job_id)

    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table as RLTable, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    small = styles["BodyText"]
    small.fontSize = 8
    story = [
        Paragraph("MediTrans Ontario — Chain of Custody Record", styles["Title"]),
        Paragraph(f"Job ID: {job['id']} · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by {current_user.get('email')}", small),
        Spacer(1, 12),
        Paragraph("Job Details", styles["Heading2"]),
    ]
    detail_rows = [
        ["Delivery", job.get("title") or "Medical transport"],
        ["Status", job.get("status", "")],
        ["Facility", (facility or {}).get("name") or "Direct booking"],
        ["Pickup", job.get("pickup_address") or ""],
        ["Dropoff", job.get("delivery_address") or job.get("dropoff_address") or ""],
        ["Handling flags", ", ".join(job.get("handling_flags") or []) or "none"],
        ["Recipient", job.get("recipient_name") or "—"],
        ["Created", (job.get("created_at") or "")[:19].replace("T", " ")],
        ["Delivered", (job.get("delivered_at") or job.get("completed_at") or "—")[:19].replace("T", " ")],
    ]
    t = RLTable(detail_rows, colWidths=[1.5 * inch, 5 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
    ]))
    story += [t, Spacer(1, 12), Paragraph("Custody Events", styles["Heading2"])]
    ev_rows = [["Time (UTC)", "Event", "Actor", "GPS", "Recipient", "Evidence", "Notes"]]
    for e in events:
        actor = users.get(e.get("actor_id"), {})
        gps = f"{e.get('gps_lat'):.5f},{e.get('gps_lng'):.5f}" if e.get("gps_lat") is not None else "—"
        ev_rows.append([
            (e.get("timestamp") or "")[:19].replace("T", " "),
            e.get("event_type", ""),
            actor.get("full_name") or e.get("actor_id", "")[:8],
            gps,
            e.get("recipient_name") or "—",
            "yes" if e.get("evidence_url") else "no",
            (e.get("notes") or "")[:60]
        ])
    t2 = RLTable(ev_rows, colWidths=[1.1 * inch, 1.0 * inch, 1.0 * inch, 1.1 * inch, 0.9 * inch, 0.5 * inch, 1.4 * inch])
    t2.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ]))
    story += [t2, Spacer(1, 12), Paragraph("Access & Change History (Audit Trail)", styles["Heading2"])]
    au_rows = [["Time (UTC)", "Actor", "Role", "Action", "Entity"]]
    for a in audits[-60:]:
        u = users.get(a["actor_id"], {})
        au_rows.append([
            (a.get("timestamp") or "")[:19].replace("T", " "),
            u.get("full_name") or u.get("email") or a["actor_id"][:8],
            a.get("actor_role", ""),
            a.get("action", ""),
            a.get("entity", "")
        ])
    t3 = RLTable(au_rows, colWidths=[1.3 * inch, 1.7 * inch, 0.9 * inch, 0.9 * inch, 1.4 * inch])
    t3.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ]))
    story.append(t3)
    doc.build(story)
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=custody-record-{job_id[:8]}.pdf"})

@api_router.get("/admin/compliance/breach-report")
async def compliance_breach_report(date_from: str, date_to: str, format: Optional[str] = None,
                                   request: Request = None, auth: Optional[str] = Query(None)):
    if auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
            if not current_user:
                raise HTTPException(status_code=401, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        current_user = await get_current_user(request)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")
    jobs = await db.jobs.find({"created_at": {"$gte": date_from, "$lte": date_to + "T23:59:59.999999+00:00"}}, {"_id": 0}).to_list(20000)
    fac_ids = list({j.get("facility_id") for j in jobs if j.get("facility_id")})
    facilities = {f["id"]: f async for f in db.facilities.find({"id": {"$in": fac_ids}}, {"_id": 0, "id": 1, "name": 1, "billing_email": 1})}
    duids = list({j.get("accepted_by") or j.get("assigned_driver_id") for j in jobs})
    users = {u["id"]: u async for u in db.users.find({"id": {"$in": duids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})}
    records = []
    for j in jobs:
        did = j.get("accepted_by") or j.get("assigned_driver_id")
        has_pii = bool((j.get("recipient_name") and j.get("recipient_name") != REDACTED) or
                       (j.get("recipient_phone") and j.get("recipient_phone") != REDACTED))
        records.append({
            "job_id": j["id"],
            "created_at": j.get("created_at"),
            "status": j.get("status"),
            "facility_name": facilities.get(j.get("facility_id"), {}).get("name") or "Direct booking",
            "driver_name": users.get(did, {}).get("full_name"),
            "pickup_address": j.get("pickup_address"),
            "delivery_address": j.get("delivery_address") or j.get("dropoff_address"),
            "recipient_name": j.get("recipient_name") or "—",
            "recipient_phone": j.get("recipient_phone") or "—",
            "contains_personal_data": has_pii,
            "data_purged": bool(j.get("data_purged"))
        })
    summary = {
        "date_from": date_from, "date_to": date_to,
        "affected_jobs": len(records),
        "jobs_with_personal_data": sum(1 for r in records if r["contains_personal_data"]),
        "unique_recipients": len({r["recipient_name"] for r in records if r["contains_personal_data"]}),
        "drivers_involved": len({r["driver_name"] for r in records if r["driver_name"]}),
        "facilities_involved": len({r["facility_name"] for r in records})
    }
    await log_audit(current_user, "export" if format == "csv" else "view", "breach_report", f"{date_from}_{date_to}", details=summary)
    if format == "csv":
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["MediTrans Ontario — Breach Report (affected records)", f"{date_from} to {date_to}"])
        w.writerow(["Affected jobs", summary["affected_jobs"], "With personal data", summary["jobs_with_personal_data"],
                    "Unique recipients", summary["unique_recipients"], "Drivers", summary["drivers_involved"], "Facilities", summary["facilities_involved"]])
        w.writerow([])
        w.writerow(["Job ID", "Created", "Status", "Facility", "Driver", "Pickup", "Delivery", "Recipient", "Recipient Phone", "Contains Personal Data", "Purged"])
        for r in records:
            w.writerow([r["job_id"], (r["created_at"] or "")[:19], r["status"], r["facility_name"], r["driver_name"] or "",
                        r["pickup_address"] or "", r["delivery_address"] or "", r["recipient_name"], r["recipient_phone"],
                        "yes" if r["contains_personal_data"] else "no", "yes" if r["data_purged"] else "no"])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=breach-report-{date_from}-{date_to}.csv"})
    return {"summary": summary, "records": records}

@api_router.get("/dispatch/board")
async def dispatch_board(staff: dict = Depends(require_staff)):
    jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)
    fac_ids = list({j["facility_id"] for j in jobs if j.get("facility_id")})
    fac_names = {f["id"]: f["name"] async for f in db.facilities.find({"id": {"$in": fac_ids}}, {"_id": 0, "id": 1, "name": 1})}
    driver_ids = list({j.get("assigned_driver_id") or j.get("accepted_by") for j in jobs if j.get("assigned_driver_id") or j.get("accepted_by")})
    names = {u["id"]: u["full_name"] async for u in db.users.find({"id": {"$in": driver_ids}}, {"_id": 0, "id": 1, "full_name": 1})}
    for j in jobs:
        j["facility_name"] = fac_names.get(j.get("facility_id"))
        did = j.get("assigned_driver_id") or j.get("accepted_by")
        j["driver_name"] = names.get(did) if did else None
        j["status_since"] = (
            j.get("delivered_at") if j["status"] in ("delivered", "completed", "returned") else
            j.get("cancelled_at") if j["status"] == "cancelled" else
            j.get("picked_up_at") if j["status"] in ("picked_up", "in_transit") else
            j.get("accepted_at") if j["status"] in ("accepted", "in_progress") else
            j.get("offered_at") if j["status"] == "offered" else
            j.get("created_at")
        ) or j.get("created_at")
    recs = await db.drivers.find({"verification_status": "approved"}, {"_id": 0, "user_id": 1, "verification_status": 1, "insurance_expiry": 1}).to_list(200)
    duids = [r["user_id"] for r in recs if not driver_compliance_issues(r)]
    dnames = {u["id"]: u["full_name"] async for u in db.users.find({"id": {"$in": duids}, "role": "driver"}, {"_id": 0, "id": 1, "full_name": 1})}
    approved_drivers = [{"user_id": uid, "name": dnames[uid]} for uid in duids if uid in dnames]
    return {"jobs": jobs, "approved_drivers": approved_drivers}

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
    # Seed permits collection from ONTARIO_PERMITS defaults if empty
    if await db.permits.count_documents({}) == 0:
        for idx, p in enumerate(ONTARIO_PERMITS):
            doc = {**p, "order": idx + 1,
                   "created_at": datetime.now(timezone.utc).isoformat()}
            await db.permits.insert_one(doc)
    # Clean up legacy subscription_plans settings doc (revenue model switched to commission)
    await db.settings.delete_one({"key": "subscription_plans"})
    # Remove stale subscription fields from users (cosmetic cleanup, harmless if absent)
    await db.users.update_many({}, {"$unset": {
        "subscription_plan": "", "subscription_status": "", "subscription_expires": ""
    }})
    # Backfill status on existing users (marketplace data model)
    await db.users.update_many({"status": {"$exists": False}}, {"$set": {"status": "approved"}})
    # Audit log indexes (compliance)
    await db.audit_logs.create_index("entity_id")
    await db.audit_logs.create_index("actor_id")
    await db.audit_logs.create_index("timestamp")
    # Job query indexes
    await db.jobs.create_index("status")
    await db.jobs.create_index("accepted_by")
    await db.jobs.create_index("assigned_driver_id")
    await db.jobs.create_index("posted_by")
    await db.jobs.create_index("facility_id")
    # Custody chain indexes
    await db.custody_events.create_index("job_id")
    await db.custody_events.create_index("timestamp")
    # Driver documents index
    await db.driver_documents.create_index([("user_id", 1), ("doc_type", 1)])
    # Daily data-retention purge (compliance)
    asyncio.create_task(retention_purge_loop())
    # Init object storage for driver documents
    try:
        await asyncio.to_thread(init_storage)
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Object storage init failed: {e}")
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
