# Test Credentials — MediTrans Ontario

## Admin (creator)
- Email: `gabrielosmanhamza@yahoo.com`
- Password: `Admin@123`
- Role: `admin` (auto-promoted via `ADMIN_EMAIL` env var)
- Admin URL: `/admin`

Notes: Any user created with the email in `ADMIN_EMAIL` (backend/.env) is auto-promoted to `admin` on register or login.

## Driver (regular test user)
- Email: `driver1@test.com`
- Password: `Driver@123`
- Role: `driver`
- Has an approved driver record in `db.drivers` (verification_status=approved) so it CAN accept jobs.
- Home: `/dashboard`

## Unverified Driver (onboarding testing)
- Email: `newdriver@test.com`
- Password: `NewDriver@123`
- Role: `driver`, verification_status: `incomplete`
- Lands on `/onboarding`; blocked from /dashboard and /jobs until an admin/dispatcher approves via Admin → Drivers tab.

## Facility (test user)
- Email: `facility1@test.com`
- Password: `Facility@123`
- Role: `facility`
- Home: `/facility` — full Facility Portal (Book Transport form + request list). Owns facility "LifeLabs Queen West" (455 Queen St W, Toronto).

## Dispatcher (test user)
- Email: `dispatcher1@test.com`
- Password: `Dispatch@123`
- Role: `dispatcher`
- Home: `/dispatch` — full Kanban operations board (Open Pool → Offered → Accepted → Picked Up → In Transit → Delivered → Exceptions) with assign/reassign, cancel-with-confirm, custody timelines.

## RBAC notes
- Drivers with no approved driver record (verification_status != approved) get 403 on `POST /api/jobs/{id}/accept` and cannot be assigned via `PUT /api/jobs/{id}`.
- Drivers cannot `POST /api/jobs` (403). Facilities/dispatchers/admins can.
- `GET /api/audit-logs` requires admin or dispatcher role.
