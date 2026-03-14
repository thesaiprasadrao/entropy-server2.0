# Entropy Deployment Checklist

Work through this top-to-bottom before going live. Each section must be fully
checked before the next one begins.

---

## 1. Secrets & Credentials

- [ ] Rotate `ADMIN_SECRET_KEY` — replace with a 256-char random string
  ```
  openssl rand -hex 128
  ```
- [ ] Rotate `POSTGRES_PASSWORD` — replace with a 256-char random string
- [ ] Rotate all Groq API keys in `LLM_API_KEYS` (one or more keys were exposed in this session)
- [ ] Rotate `CTFD_SECRET_KEY` — replace with a long random string
- [ ] Change `CTFD_ADMIN_EMAIL` and `CTFD_ADMIN_PASSWORD` from defaults
- [ ] Confirm `.env` is **not** committed (`git status` should not show `.env`)
- [ ] Confirm `.env` is listed in `.gitignore` (it is)

---

## 2. Environment / Config

- [ ] Set `ALLOW_UNKNOWN_TEAMS=false` in `.env` if you want to lock down to pre-seeded teams only
  - Leave as `true` (the default) only if any CTFd-registered user should be allowed in
- [ ] Verify `DATABASE_URL` points to the correct host/db for the target environment
- [ ] Verify `LLM_API_KEYS` contains valid, unrotated Groq keys with sufficient quota
- [ ] Confirm `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` all match `DATABASE_URL`

---

## 3. TLS / Networking

- [ ] Put TLS termination in front of Nginx (reverse proxy, load balancer, or Certbot on the host)
  - Nginx currently listens on port 80 only — participants will send cookies over plain HTTP without TLS
- [ ] Update Nginx `server_name` from `localhost` to the real domain name
- [ ] If behind a load balancer, verify `X-Forwarded-For` is trusted only from the LB IP
  - The rate limiter uses `X-Forwarded-For` — spoofable if not locked down
- [ ] Confirm port 5432 (Postgres) is bound to `127.0.0.1` only — it already is in `docker-compose.yml`
- [ ] Confirm port 8000 (backend) is **not** published to the host — it is not in `docker-compose.yml`

---

## 4. Database & Migrations

- [ ] Run Alembic migrations on the target DB before starting the backend:
  ```
  docker compose exec backend alembic upgrade head
  ```
- [ ] Verify all migrations apply cleanly with no errors
- [ ] Confirm the `user_hints` unique constraint migration ran:
  `20260314_0001_c3d4e5f6a7b8_add_unique_user_hint_user_level.py`
- [ ] (Optional) Take a pre-event DB backup:
  ```
  ./scripts/backup_postgres.sh
  ```

---

## 5. CTFd Setup

- [ ] First-time setup: open CTFd at `http://<host>/` and complete the setup wizard
- [ ] Log in as CTFd admin and verify the admin panel is accessible at `/admin/`
- [ ] Confirm CTFd `SECRET_KEY` matches the one in `.env`
- [ ] Verify CTFd challenges sync correctly (runs automatically 5 s after backend starts):
  ```
  docker compose logs -f backend | grep -i sync
  ```
  Or run manually:
  ```
  docker compose exec backend python3 -m app.scripts.sync_ctfd
  ```
- [ ] Verify all levels appear in CTFd's challenge list with the correct flags
- [ ] Set CTFd event start/end times in the admin panel

---

## 6. Teams / Users

- [ ] Decide on team registration mode:
  - **Open** (`ALLOW_UNKNOWN_TEAMS=true`): any CTFd-registered user can play
  - **Closed** (`ALLOW_UNKNOWN_TEAMS=false`): pre-seed teams from a CSV first
- [ ] If using closed mode, seed teams:
  ```
  docker compose exec backend python3 seed_teams.py teams.csv
  ```
- [ ] Verify seeded teams appear in the backend DB (no duplicates)

---

## 7. Levels & Flags

- [ ] Review `levels.yaml` — ensure all flags in the pools are unique across all levels
- [ ] Verify `max_input_tokens: 200` is set on hard levels (7–10) — it is as of the latest commit
- [ ] Confirm level 1 system prompt behaviour is intentional (it currently instructs the LLM to reveal the flag)
- [ ] Verify LLM model names in `levels.yaml` are valid Groq model IDs
- [ ] Spot-check a few levels end-to-end manually (open level → chat → submit flag)

---

## 8. Smoke Tests

- [ ] `GET /health` returns `200 OK`
- [ ] Unauthenticated `GET /levels/list` returns `401`
- [ ] Login via CTFd, then `GET /levels/list` returns the level list
- [ ] Open a level, chat with the LLM, receive a response
- [ ] Submit the correct flag for a level — verify it marks as solved in CTFd scoreboard
- [ ] Submit a wrong flag — verify it returns an error and does not mark as solved
- [ ] Verify rate limit fires on rapid chat requests (5 s cooldown)
- [ ] Verify admin route `GET /admin/state/global_shutdown` requires `X-Admin-Token` header
- [ ] Set `global_shutdown=true` via admin API and verify `/levels/list` returns `503`
- [ ] Verify `/docs` and `/redoc` return `404`

---

## 9. Load Testing (optional but recommended)

- [ ] Run Locust against a staging environment before the live event:
  ```
  pip install locust
  locust -f locustfile.py --host http://localhost --users 100 --spawn-rate 10 --run-time 60s --headless --only-summary
  ```
- [ ] Verify Groq API quota can sustain expected concurrent users

---

## 10. Operational Readiness

- [ ] Confirm `docker compose up --build -d` starts all 4 services cleanly
- [ ] Confirm all containers are healthy: `docker compose ps`
- [ ] Set up log monitoring / alerting (`docker compose logs -f backend`)
- [ ] Know how to trigger a maintenance window:
  ```
  curl -X POST http://<host>/admin/state/global_shutdown \
    -H "X-Admin-Token: <ADMIN_SECRET_KEY>" \
    -H "Content-Type: application/json" \
    -d '{"value": "true"}'
  ```
- [ ] Know how to pause the AI without full shutdown:
  ```
  curl -X POST http://<host>/admin/state/pause_ai \
    -H "X-Admin-Token: <ADMIN_SECRET_KEY>" \
    -H "Content-Type: application/json" \
    -d '{"value": "true"}'
  ```
- [ ] Backup script is accessible and tested: `./scripts/backup_postgres.sh`
- [ ] CTFd SQLite DB is in the `./ctfd/` bind-mount — confirm it is included in backups

---

## Known Deferred Issues (pre-contest awareness)

| Issue | Risk | Notes |
|-------|------|-------|
| No TLS | HIGH | Cookies and flags sent in plaintext over HTTP |
| In-memory rate limiter | MEDIUM | Ineffective if running multiple uvicorn workers; single worker is fine |
| Flags stored in plaintext in DB | LOW | Intentional CTF design |
| CTFd on SQLite | LOW | Adequate for small events; swap to Postgres for large scale |
