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
import stripe
import resend
import asyncio
import hashlib
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
DRIVER_VERIFICATION_STATUSES = {"incomplete", "pending_review", "approved", "rejected"}
COMPLIANCE_STATUSES = {"not_submitted", "pending", "valid", "expired", "rejected"}

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
    "delivered_at", "completed_at", "accepted_by", "assigned_driver_id", "facility_id"
}

def scoped_job(job: dict, user: dict) -> dict:
    if user.get("role") == "driver":
        return {k: v for k, v in job.items() if k in DRIVER_JOB_FIELDS}
    return job

async def log_audit(actor: dict, action: str, entity: str, entity_id: str):
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "actor_id": actor["id"],
            "actor_role": actor.get("role"),
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logging.getLogger(__name__).error(f"Audit log write failed: {e}")

async def is_driver_verified(user_id: str) -> bool:
    rec = await db.drivers.find_one({"user_id": user_id}, {"_id": 0, "verification_status": 1})
    return bool(rec and rec.get("verification_status") == "approved")

async def facility_ids_owned_by(user_id: str) -> list:
    return [f["id"] async for f in db.facilities.find({"owner_user_id": user_id}, {"_id": 0, "id": 1})]

def strip_facility_billing(fac: dict, user: dict) -> dict:
    if user.get("role") in STAFF_ROLES or fac.get("owner_user_id") == user["id"]:
        return fac
    return {k: v for k, v in fac.items() if k != "billing_email"}

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
    if job.get("status") != "completed":
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
    if job.get("status") != "completed":
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
    if job.get("status") != "completed":
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
    if job.get("status") != "completed":
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
    query = {"status": "open"}
    if current_user.get("role") == "facility":
        fac_ids = await facility_ids_owned_by(current_user["id"])
        query = {"status": "open", "$or": [{"posted_by": current_user["id"]}, {"facility_id": {"$in": fac_ids}}]}
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    await log_audit(current_user, "view", "job", "list")
    return {"jobs": [scoped_job(j, current_user) for j in jobs]}

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
        raise HTTPException(status_code=403, detail="Your driver verification is not approved yet. Complete verification before accepting jobs.")
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
            "assigned_driver_id": current_user["id"],
            "accepted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    await log_audit(current_user, "accept", "job", job_id)
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": scoped_job(updated_job, current_user)}

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
    if job.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="Only in-progress jobs can be completed")
    
    now = datetime.now(timezone.utc)
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "completed",
            "completed_at": now.isoformat(),
            "delivered_at": now.isoformat()
        }}
    )
    await log_audit(current_user, "complete", "job", job_id)
    await db.drivers.update_one({"user_id": current_user["id"]}, {"$inc": {"total_trips": 1}})
    
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
    await db.drivers.delete_one({"user_id": user_id})
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
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not is_admin:
        for f in ("verification_status", "rating_avg", "total_trips"):
            updates.pop(f, None)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db.drivers.update_one({"user_id": user_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Driver record not found")
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
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.facilities.update_one({"id": facility_id}, {"$set": updates})
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
    await log_audit(current_user, "view", "job", job_id)
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
        raise HTTPException(status_code=400, detail="Cannot assign job: driver verification is not approved")
    if new_status in ("offered", "accepted") and role != "driver":
        if not target_driver:
            raise HTTPException(status_code=400, detail="Assign a driver before offering the job")
        if not await is_driver_verified(target_driver):
            raise HTTPException(status_code=400, detail="Cannot offer job: driver verification is not approved")
    if "dropoff_address" in updates:
        updates["delivery_address"] = updates["dropoff_address"]
    if "payout_amount" in updates:
        updates["offered_price"] = updates["payout_amount"]
    if "distance_km" in updates:
        updates["estimated_distance_km"] = updates["distance_km"]
    if "assigned_driver_id" in updates:
        updates["accepted_by"] = updates["assigned_driver_id"]
    now = datetime.now(timezone.utc).isoformat()
    if new_status == "accepted" and not job.get("accepted_at"):
        updates["accepted_at"] = now
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
    await log_audit(current_user, "delete", "job", job_id)
    return {"status": "deleted", "job_id": job_id}

# ---- Audit logs (compliance) ----
@api_router.get("/audit-logs")
async def get_audit_logs(
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
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
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(min(limit, 1000))
    return {"logs": logs, "count": len(logs)}

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
