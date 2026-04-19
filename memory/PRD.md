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
