# MediTrans Ontario - Medical Transportation Platform

## Original Problem Statement
Build an app for medical transportation that people can register and pay a monthly subscription as drivers to move medical and biological products in the Province of Ontario, Canada. The application should work like Uber taxi but for transporting medical goods, prospective or potential drivers should be able to access all required permits and licenses required by the Province of Ontario in Canada. The application should have a billing and charges section that includes agreed fees with drivers.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + MongoDB
- **Payments**: Stripe (emergentintegrations library)
- **Authentication**: JWT-based

## User Personas
1. **Driver**: Medical transport professional seeking jobs
2. **Healthcare Facility**: Posts medical transport requests (future)
3. **Admin (Creator)**: Platform management — auto-promoted via `ADMIN_EMAIL` env

## Core Requirements (Static)
- Driver registration with JWT authentication
- Ontario permit/license requirements checklist
- **Commission-based revenue model**: 20% platform commission on completed trips
- **Cancellation policy**: 5-minute grace window after accepting a job; $15 late-cancellation fee after that
- Job posting and accepting system (no subscription required)
- Driver balance & ledger (commission + cancellation fees)
- Pay-off-balance via Stripe Checkout
- Admin (creator) auto-promoted via `ADMIN_EMAIL` env var

## What's Been Implemented (January 2026)

### Backend APIs
- `/api/auth/register` - Driver registration
- `/api/auth/login` - JWT login
- `/api/auth/me` - Get current user
- `/api/permits` - Ontario permit requirements
- `/api/driver/permits` - Driver permit tracking
- `/api/subscriptions/plans` - Subscription tiers
- `/api/payments/checkout` - Stripe checkout
- `/api/payments/status/{session_id}` - Payment verification
- `/api/payments/history` - Transaction history
- `/api/jobs` - Job CRUD operations
- `/api/jobs/available` - Available jobs
- `/api/jobs/{id}/accept` - Accept job
- `/api/jobs/{id}/complete` - Complete job

### Admin APIs (Feb 2026)
- `/api/admin/stats` - Users, jobs, revenue summary
- `/api/admin/users` + PUT/DELETE - User management (role, subscription)
- `/api/admin/jobs` + PUT/DELETE - Job oversight
- `/api/admin/plans` + PUT - Edit subscription tier pricing/features (DB-backed)
- `/api/admin/fees` + PUT - Edit platform fee agreement (DB-backed)
- `/api/admin/transactions` - Payment audit
- All protected by `require_admin` dependency; non-admins receive 403

### Admin UI (Feb 2026)
- `/admin` route with `AdminRoute` guard (role='admin' only)
- `AdminDashboardPage.js`: Stats cards + tabs (Users, Jobs, Fees & Commission, Ledger, Transactions)
- Edit dialogs for users/jobs with confirm-delete AlertDialogs
- Admin badge + nav link shown conditionally on Dashboard

### Commission Model Pivot (Feb 19 2026)
- **Removed**: Subscription plans (Basic/Pro/Premium), `/api/subscriptions/plans`, `/api/admin/plans`, subscription gating on job acceptance
- **Added**: Commission-based revenue — 20% of every completed trip recorded in `ledger` collection as `{type:'commission', status:'owed'}`
- **Added**: Cancellation flow — `/api/jobs/{id}/cancel` with 5-min grace (free) or $15 fee after
- **Added**: `/api/driver/balance` shows owed/paid totals + full ledger entries
- **Added**: `/api/payments/balance/checkout` — Stripe Checkout to pay off outstanding balance; on paid, settles matching ledger entries
- **Added**: `/api/admin/ledger` + stats updated with `commission_owed/paid`, `cancellation_fees_owed/paid`, `total_outstanding`
- **Admin-editable**: commission rate, cancellation fee, grace window via Fees tab
- **Frontend**: BillingPage rewritten (balance + ledger + fee agreement); JobsPage adds Cancel button with grace countdown; Dashboard shows balance alert; Landing page swapped subscription tiers for commission messaging

### Permits Editor + Real-Time Urgent Jobs (Feb 19 2026)
- **Backend**: Ontario permits migrated from hardcoded `ONTARIO_PERMITS` list to `db.permits` collection (seeded on first startup). Full admin CRUD: `GET/POST/PUT/DELETE /api/admin/permits`. Public `/api/permits` reads from DB.
- **Admin UI**: New **Permits** tab with Add/Edit/Delete dialogs (confirm-delete AlertDialog, required-flag checkbox). All 6 Ontario permits editable live.
- **Frontend**: New `useUrgentJobAlerts` hook (15s polling) wired into Dashboard + Jobs pages. On newly posted urgent/emergency jobs: sonner toast (red for emergency, amber for urgent) + red "Urgent Jobs" banner on Dashboard with Dismiss / View All buttons.
- **Bug fix**: `/api/jobs/{id}/cancel` now returns 400 for cancelling an open job (was 403).
- **Tested**: 10/10 backend pytest + 10/10 frontend Playwright — zero issues.

### Tip Your Driver (Feb 19 2026)
- **Public endpoints** (no auth): `GET /api/tips/info/{job_id}`, `POST /api/tips/checkout/{job_id}`, `GET /api/tips/status/{session_id}`
- **Authed endpoint**: `GET /api/driver/tips` — list + total of tips received
- **Revenue model**: 100% of tip → driver earnings (no platform commission on tips). Credited to `earnings` collection with `type='tip'` on Stripe paid confirmation. Idempotent via `payment_session_id` check.
- **Frontend**: New public `/tip/:jobId` page with 15/20/25% presets + custom, optional tipper name, Stripe Checkout redirect, thank-you screen on success. JobsPage adds "Share Tip Link" button on completed jobs (copies URL). Dashboard has new "Tips Received" stat card; grid expanded to 5 cols on xl.
- **Tested**: 13/13 backend pytest + 16/17 frontend Playwright — zero issues.

### Stripe Connect — Express Accounts (Feb 19 2026)
- **Backend**: Installed official `stripe==14.3.0` SDK alongside emergent integrations. `STRIPE_API_KEY` now set to the creator's platform test key so all Stripe calls (Checkout + Connect) route to their account.
- **New endpoints**: `POST /api/driver/connect/onboard` (creates CA Express account on first call, reuses thereafter, returns Stripe-hosted onboarding URL), `GET /api/driver/connect/status` (syncs charges_enabled/payouts_enabled/requirements from Stripe into user doc), `POST /api/driver/connect/login-link` (one-time link to Stripe Express dashboard).
- **Tip routing**: `POST /api/tips/checkout` now uses Stripe **destination charges** (`transfer_data.destination`) when the driver has `stripe_charges_enabled=true`. Response includes `routed_to_driver:true`, `stripe_account_id`. Fallback to emergent Checkout when driver is not yet onboarded.
- **Frontend**: New "Stripe Payouts" card on `/billing` with three states — Not Connected (blue "Connect Stripe" CTA) / Onboarding Incomplete (amber "Finish Onboarding") / Active (green badge + "Stripe Dashboard" button that opens one-time login link). Return-URL handler toasts success when driver comes back from Stripe.
- **Tested**: 16/16 backend pytest + 3/3 frontend UI states — zero issues.

### Driver Ratings & Reviews (Feb 19 2026)
- **Backend**: New `reviews` collection. Public endpoints `GET /api/reviews/info/{job_id}`, `POST /api/reviews/{job_id}` (1-5 stars, optional comment + reviewer name; one review per trip; completed-trip only). `GET /api/drivers/{id}/reviews` for public driver rating page. `GET /api/driver/reviews` for driver's own feed. Admin moderation: `GET /api/admin/reviews`, `POST /api/admin/reviews/{id}/hide` (soft), `DELETE /api/admin/reviews/{id}` (hard).
- **Frontend**: New public `/rate/:jobId` page with interactive `StarRating` component + comment + reviewer name. Tip page success screen now shows a post-tip rating prompt; main tip view has a "Don't want to tip? Rate X instead" fallback link. Dashboard has new "Your Rating" stat card (★ avg + review count). Admin dashboard has new **Reviews** tab with hide (EyeOff) + delete (confirm AlertDialog) actions.
- **Tested**: 23/23 backend pytest + 7/7 frontend Playwright flows — zero issues.

### Capacitor Mobile Wrap (Feb 19 2026)
- **Packages installed**: `@capacitor/core@^7`, `@capacitor/cli@^7`, `@capacitor/ios@^7`, `@capacitor/android@^7` (Capacitor 8 required Node 22, not available in this env).
- **Config**: `frontend/capacitor.config.json` — `appId=ca.meditrans.app`, `appName=MediTrans`, `webDir=build`.
- **Scaffolded**: `frontend/ios/App/App.xcworkspace` (ready to open in Xcode on Mac), `frontend/android/` (ready to open in Android Studio).
- **Scripts**: `yarn build:mobile` (build + sync), `yarn ios:open`, `yarn android:open`.
- **Guide**: `/app/MOBILE.md` — full walkthrough from `git clone` on Mac → Xcode signing → App Store submission, including Stripe-is-allowed note for physical-service payments.
- **No native features yet**: network-only permissions; camera/location/push can be added when needed via Capacitor plugins.
- `/api/fees/agreement` - Platform fee structure
- `/api/earnings` - Driver earnings
- `/api/earnings/stats` - Earnings statistics

### Frontend Pages
- Landing page with hero, features, pricing, Ontario compliance
- Login/Register pages
- Driver Dashboard with stats and job listings
- Jobs page with available/my jobs tabs
- Permits page with compliance checklist
- Billing page with subscription management

### Ontario Permits Integrated
1. CVOR (Commercial Vehicle Operator's Registration)
2. TDG Certificate (Transportation of Dangerous Goods)
3. Ontario Driver's License (Class G+)
4. Vulnerable Sector Check
5. Commercial Vehicle Insurance
6. First Aid & CPR (optional)

### Marketplace Shared Data Model (June 2026)
- **Enums**: user roles (driver/facility/dispatcher/admin), user status (pending/approved/suspended), facility types (pharmacy/clinic/lab/hospital/health_shop/other), item categories (prescription/lab_sample/biological/medical_equipment/medical_supply/other), handling flags (cold_chain/controlled_substance/fragile/urgent/signature_required/id_required), job statuses (created/offered/accepted/picked_up/in_transit/delivered/cancelled/returned + legacy open/completed), driver verification (incomplete/pending_review/approved/rejected), compliance statuses (not_submitted/pending/valid/expired/rejected)
- **USERS extended**: `status` field added (existing users backfilled to approved on startup); new roles facility & dispatcher accepted. Admin CRUD: `POST/GET /api/users` (role/status filters), `GET/PUT/DELETE /api/users/{id}`
- **DRIVERS collection** (`db.drivers`, keyed by user_id): vehicle_type, vehicle_plate, cvor_status, tdg_cert_status, vulnerable_sector_check_status, insurance_status, insurance_expiry, cold_chain_certified, verification_status, rating_avg, total_trips. CRUD: `POST /api/drivers` (driver self or admin), `GET /api/drivers` (admin, filter verification_status), `GET/PUT/DELETE /api/drivers/{user_id}/record`. Drivers cannot self-set verification_status/rating/trips (admin only)
- **FACILITIES collection** (`db.facilities`): name, type, address, contact_name, contact_phone, billing_email, status, owner_user_id. Full CRUD at `/api/facilities` (owner/admin for update/delete)
- **JOBS extended additively**: facility_id (validated to exist), item_category, handling_flags, distance_km, payout_amount, special_instructions ("non-clinical handling notes only" — no clinical/PHI fields), assigned_driver_id, picked_up_at, delivered_at. Legacy aliases auto-synced both ways: dropoff_address↔delivery_address, payout_amount↔offered_price, distance_km↔estimated_distance_km, assigned_driver_id↔accepted_by. New endpoints: `GET/PUT/DELETE /api/jobs/{id}`; PUT auto-stamps accepted_at/picked_up_at/delivered_at on status transitions. Old driver UI payloads/statuses fully backward compatible
- **No UI built yet** (per user request). Tested via full curl smoke suite (users/drivers/facilities/jobs CRUD, enum 422 validation, RBAC 403s, lifecycle timestamps, legacy compat) — all passing

### RBAC + Role Routing + Job Audit Log (June 2026)
- **Role guards**: `require_staff` (admin|dispatcher) added alongside `require_admin`. Four roles fully supported: driver, facility, dispatcher, admin
- **Role-based login routing**: `roleHome()` in AuthContext — admin→/admin, facility→/facility (placeholder Facility Portal), dispatcher→/dispatch (placeholder Dispatch Console), driver→/dashboard. `RoleRoute` guard in App.js redirects cross-role access to the user's own home. Test users: facility1@test.com, dispatcher1@test.com (see test_credentials.md)
- **Job data scoping (API level)**: drivers see only open jobs + their own, with a logistics-fields whitelist (no posted_by, no billing data); facilities see only jobs they posted or for facilities they own; staff (dispatcher/admin) see everything. Facility billing_email stripped from /api/facilities for non-owner non-staff callers; facility role lists only own facilities
- **Verification gating**: drivers without an approved `drivers` record get 403 on job accept; PUT assignment/offer of an unverified driver returns 400
- **Drivers cannot POST /api/jobs** (403); drivers can PUT only `status` on their assigned jobs
- **Audit log** (`db.audit_logs`: id, actor_id, actor_role, action, entity, entity_id, timestamp) written on every job create/update/view/accept/cancel/complete/delete — write is fail-safe (never breaks the request). `GET /api/audit-logs` (staff only) with entity/entity_id/actor_id/action filters. Indexes on audit_logs + jobs query fields
- **Tested**: 30/30 backend pytest (`/app/backend/tests/test_rbac_marketplace.py`, reusable regression suite) + all frontend role-login/guard/logout flows via Playwright — zero issues (iteration_9)
- **Known note**: visual-edits babel plugin crashes on component-as-prop patterns across files — placeholder pages kept self-contained

### Chain-of-Custody Events (June 2026)
- **New `custody_events` collection** (append-only, legal chain-of-custody per delivery): id, job_id, event_type (pickup_confirmed | in_transit_ping | delivery_attempted | delivered | returned | exception), timestamp (server-set), gps_lat/gps_lng (range-validated), actor_id (server-set from token), evidence_url (signature/photo/ID capture), recipient_name, recipient_relationship, notes
- **Endpoints**: `POST /api/jobs/{id}/custody-events` (assigned driver or staff only; facilities 403), `GET /api/jobs/{id}/custody-events` (chronological, job-access scoped), `GET /api/custody-events/{id}`. PUT/PATCH/DELETE return **405 "append-only"** — records are immutable once created
- Every custody-event creation is also written to the audit log (entity=custody_event). Indexes on job_id + timestamp
- **Tested**: 13/13 curl smoke checks + 30/30 RBAC regression suite re-run — zero issues

### Driver Onboarding & Verification (June 2026)
- **Mobile-first /onboarding checklist** (OnboardingPage.js): 7 credentials — driver's licence, vehicle registration + plate (plate text input), CVOR, TDG certificate, vulnerable sector check, commercial insurance (expiry date required, min $2M label), optional cold-chain cert ("unlocks cold-chain jobs"). Status badges missing/pending/approved/rejected, rejection reasons shown, Replace re-upload, progress bar, blue "Verification in progress" holding banner once all 6 required are in; polls every 15s and auto-redirects to /dashboard on approval
- **Gating**: unapproved drivers (verification_status ≠ approved) are redirected from /dashboard and /jobs to /onboarding (VerifiedDriverRoute); roleHome sends them to /onboarding on login/register; /auth/me + login/register responses now include verification_status
- **Storage**: Emergent Object Storage (initialized at startup via EMERGENT_LLM_KEY in backend/.env). Upload rules: JPG/PNG/WEBP/HEIC/PDF, 10MB max. Endpoints: GET /api/driver/onboarding, POST /api/driver/documents/{doc_type} (multipart; insurance_expiry + vehicle_plate form fields), GET /api/driver-documents/{id}/file (owner or staff; supports ?auth= token for browser viewing)
- **Auto-transition**: verification_status incomplete→pending_review when all required docs submitted; doc review syncs drivers compliance fields (valid/rejected) and cold_chain_certified
- **Admin "Drivers" tab** (DriverVerificationTab.jsx): per-driver rows with doc chips, view/approve/reject (reject dialog with notes), Approve/Reject Driver, revoke to review. Staff (admin+dispatcher) endpoints: GET /api/admin/driver-verifications, PUT /api/admin/driver-documents/{id}, PUT /api/admin/driver-verifications/{user_id}
- **Hardening after review**: server-side guard blocks overall approval while required docs are missing/rejected (400); user deletion cascades driver record + documents + storage blobs; every upload/view/review audit-logged
- **Tested**: iteration_10 — 18/18 onboarding pytest + 30/30 RBAC + full Playwright E2E (mobile 390px), all passed. Full backend suite now 126/126 (stale pre-pivot test_admin.py quarantined to tests_legacy/ — it mutated driver1's role and tested removed /admin/plans; commission tests updated to post jobs as admin since drivers can no longer POST /jobs)

## Prioritized Backlog

### P0 - Critical (Next Sprint)
- [ ] Admin dashboard for job posting
- [ ] Real-time job notifications
- [ ] Driver location tracking

### P1 - High Priority
- [ ] Document upload for permit verification
- [ ] In-app messaging between drivers and clients
- [ ] Route optimization
- [ ] Mobile responsiveness improvements

### P2 - Medium Priority
- [ ] Driver ratings and reviews
- [ ] Advanced analytics dashboard
- [ ] Email notifications
- [ ] Multi-language support (French)

### P3 - Low Priority
- [ ] Dark mode
- [ ] Push notifications
- [ ] Driver scheduling calendar
- [ ] API for third-party integrations

## Next Tasks
1. Add job creation functionality for clients/admins
2. Implement real-time job matching notifications
3. Add document upload for permit verification
4. Build mobile-responsive improvements
5. Add driver-client messaging
