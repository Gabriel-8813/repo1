# Learnings & Gotchas — MediTrans

## Test suite pollution (June 2026)
- `tests_legacy/test_admin.py` (quarantined) mutated driver1@test.com's role to admin mid-run and tested removed subscription endpoints (/admin/plans). If driver1 ever behaves like an admin in tests, check `db.users` role and reset to `driver`.
- Run backend suites with: `cd /app/backend && export $(grep -v '^#' /app/frontend/.env | xargs) && python -m pytest tests/ -q` (126 tests, all current).

## Visual-edits babel plugin
- Crashes ("Cannot read properties of null (reading 'traverse')") on component-as-prop patterns traced across files (e.g. `icon={IconComponent}` passed into a shared page component). Keep pages self-contained or pass rendered JSX nodes, not component references.
- PATCHED (June 2026): added null-guard at line ~876 of /app/frontend/plugins/visual-edits/babel-metadata-plugin.js (`importPath.parentPath?.parentPath || ...`). If builds crash again with this error after a plugin update, re-apply the guard. Also: rendering a destructured prop with a default (e.g. `{label}`) inside a wrapping element can trigger the same cross-file trace — prefer literals in shared components.

## Starlette request.headers caching
- `request.headers` is cached on first access; injecting headers into `request.scope` afterwards does nothing. For query-token auth (`?auth=`), decode the JWT directly instead.

## Object storage
- Emergent Object Storage initialized at startup (init_storage). Uses EMERGENT_LLM_KEY from backend/.env. Helpers: put_object/get_object/del_object in server.py, all called via asyncio.to_thread.

## RBAC invariants (do not regress)
- Drivers cannot POST /api/jobs (403) — old tests that posted jobs as drivers were updated to use the admin token.
- Job accept requires role driver (verified) or admin; sets legacy status "in_progress".
- Driver job payloads are whitelisted (DRIVER_JOB_FIELDS) — no posted_by, no billing data.
