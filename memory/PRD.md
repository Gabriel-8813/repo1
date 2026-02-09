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
3. **Admin**: Platform management (future)

## Core Requirements (Static)
- Driver registration with JWT authentication
- Ontario permit/license requirements checklist
- Monthly subscription plans ($49 Basic, $99 Pro, $149 Premium)
- Job posting and accepting system
- Billing dashboard with fee agreements
- Payment processing via Stripe

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
