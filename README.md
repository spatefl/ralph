# Sirius Asset Manager (sirius-ralph)

## Update - 2025/02

As Allegro, we continue to publish Ralph's source code and will maintain its development under a "Sources only" model, without guarantees. We believe this approach will be beneficial, allowing everyone to use and build upon the software. Our current goal is to modernize the software and ensure its long-term maintainability, and we're investing into it in 2025.

However, we are not operating under a contribution-based model. While we welcome discussions, we do not guarantee responses to issues or support for pull requests. If you require commercial support, please visit http://ralph.discourse.group.

We sincerely appreciate all past contributions that have shaped Ralph into the powerful tool it is today, and encourage the community to continue using it.

## What's new in sirius-custom (Feb 2025)

- New domain-specific Django apps for Fleet, Drones, and Sensors capture assignments, usage, maintenance, and status logs; the admin now exposes them through dedicated sitetree menus alongside placeholder Heavy Equipment categories.
- Shared lifecycle utilities (`src/ralph/lib/lifecycle/`) enforce guarded status transitions and emit structured audit trails that back the new apps.
- Local development helpers wrap Docker Compose via `make up`, `make logs`, and `make clean`, exporting `DATABASE_TEST_NAME` so Django tests run against the containerised MySQL service by default.
- Cross-cutting lifecycle models (`ComplianceRecord`, `DeploymentEntry`, `TelemetryReading`) now hang off every asset, tracking inspections, deployments, and telemetry events in one place.
- Each asset admin (Heavy Equipment, Fleet, Drones, Sensors) gained Operations, Compliance, and Telemetry tabs so maintenance logs, compliance records, deployment history, and telemetry readings are visible without leaving the detail page.
- Fleet/Drones/Heavy Equipment/Sensor APIs expose the same lifecycle data (latest maintenance/compliance/deployment/telemetry summaries) for SC3 dashboards and automation.
- Dashboard tiles render lifecycle alerts (open maintenance, expiring compliance, active deployments) so operations teams see hot spots at a glance.
- Lifecycle workflows now include approval-aware transitions (maintenance, damage, retire) that raise structured events, log `MaintenanceRecord` tickets with costs, and surface maintenance/compliance summaries in both the admin and the API responses for downstream automation.
- Deployment rosters capture shift assignments through `DeploymentEntry` + `DeploymentAssignment` logs, surface active crew in the admin/API, and auto-link telemetry events to the currently deployed team for richer utilisation metrics.
- A django-rq scheduler now auto-runs maintenance, compliance, and budget health commands; configure via `ASSETS_SCHEDULER_*` env vars and keep an `rqworker` + `rqscheduler` pair running to emit alerts and open tickets on time.
- Parts & safety management landed: spare-part inventory with auto-decrementing maintenance usage, restock alerts, procurement feeds, operator certifications, transition-gated safety checklists, and rich incident logging (attachments + follow-up tasks).
- Lifecycle analytics now compute MTTR/MTBF/time-in-state across assets and functional groups, exposing metrics through `/api/analytics/assets/…` and summarising them on the admin dashboard tiles.
- Reporting + automation suite (Phase 4): interactive reporting APIs under `/api/reporting/…`, scheduled email digests (`send_asset_digest`), configurable integration endpoints (webhooks/n8n/Celery/ERP), and SLA/predictive maintenance jobs (`check_sla`, `forecast_asset_health`) keep downstream systems and operators in sync.


## Overview

Sirius Asset Manager is a domain-focused distribution of Ralph tailored for SC3. It keeps the proven DCIM/CMDB core and adds first-class management for Heavy Equipment, Trailers, Power & Lighting, Fleet, Drones, and Sensors — plus reporting, scheduling, and integration hooks used by SC3.

Features:

* end-to-end asset lifecycle (purchase → operation → maintenance → disposal)
* flexible transitions/workflows with approvals and SLAs
* new field operations families (heavy equipment, trailers, power & lighting, fleet, drones, sensors)
* data center and back office support (upstream Ralph)
* reporting APIs, scheduled digests, snapshots, and dashboards
* integration hooks (webhooks/queues) for SC3 automations

It is an Open Source project provided on Apache v2.0 License.

[![Gitter](https://img.shields.io/gitter/room/gitterHQ/gitter.svg)](https://gitter.im/allegro/ralph?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![packagecloud](https://img.shields.io/badge/deb-packagecloud.io-844fec.svg)](https://packagecloud.io/allegro/ralph)
[![Build Status](https://github.com/allegro/ralph/actions/workflows/main.yml/badge.svg)](https://github.com/allegro/ralph/actions/workflows/main.yml)
[![Coverage Status](https://coveralls.io/repos/allegro/ralph/badge.svg?branch=ng&service=github)](https://coveralls.io/github/allegro/ralph?branch=ng)

### Local Prep Guide

The `sirius-custom` branch ships with a full dockerised stack that mirrors the service we embed inside SC3. To stand it up locally and verify the dark theme / branding before integration:

1. **Clone**
   ```bash
   git clone --branch sirius-custom https://github.com/spatefl/ralph.git sirius-assets
   cd sirius-assets
   ```

2. **Review key configuration**
   * `docker/Dockerfile-service` (Django + Node 18 build)
   * `docker/docker-compose-local-dev.yml`
   * `docker/provision/run-service.sh`
   * `docker/Dockerfile-inkpy`, `docker/Dockerfile-local-dev-static`

3. **Required containers**
| Service | Image/Build | Notes |
|---------|-------------|-------|
| `assets-web`   | `docker/Dockerfile-service` (Ubuntu Jammy, Python 3.10, Node 18) | Binds host port **8005** |
| `assets-db`    | `mysql:8.0` with `--default-authentication-plugin=mysql_native_password --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci` | |
| `assets-redis` | `redis:7.0.11` | Internal-only (no host port published) |
| `assets-inkpy` | `docker/Dockerfile-inkpy` | Worker subscribed to Redis |
| `assets-nginx` | `docker/Dockerfile-local-dev-static` | Serves `/opt/static` + `/opt/media`, proxies `/ralph/` to the web container on host **18080** |

4. **Environment / volumes**
   * Database env baked into compose (`DATABASE_NAME/USER/PASSWORD=ralph_ng`, `DATABASE_TEST_NAME=test_ralph_ng`, host `db`, port `3306`)
   * Redis env (`REDIS_HOST=redis`, port `6379`)
   * Named volume `ralph_dbdata` → `/var/lib/mysql` (persistent DB data)

5. **Build & smoke test**
   ```bash
   make up        # docker compose up --build + wait-for-db + sitetree sync
   ```
   * `run-service.sh` waits for MySQL, applies migrations, and launches `dev_ralph runserver --insecure 0.0.0.0:8005`
   * The gulp build honours `SKIP_BOWER=true` (set in the Dockerfile) so existing `bower_components/` bundles are reused; unset it locally if you need the task to fetch fresh dependencies.
   * `make logs` captures `docker ps`, `docker compose logs`, runs the frontend build, and (optionally) tails the compose output when `WATCH=1 make logs` is used.
   * Backend tests run inside the web container so they always use the containerised MySQL and Redis:
     ```bash
     docker compose -f docker/docker-compose-local-dev.yml exec assets-web venv/bin/ralph test ralph.admin.tests.test_templatetags
     ```
     The Makefile drops any stale `test_ralph_ng` database and grants the app user create/drop privileges during `make up`, so the Django test runner can recreate its schema without manual SQL.
   * Verify UI on `http://localhost:8005/login/` (direct) and `http://localhost:18080/ralph/` (nginx proxy)
   * Create a superuser as needed:
     ```bash
     docker compose -f docker/docker-compose-local-dev.yml exec assets-web venv/bin/ralph createsuperuser
     ```
   * Tear down with `make clean` (includes `docker compose down --volumes` and removes `tmp/logs/`).

6. **Firewall reminder (Ubuntu / UFW)**
   ```bash
   sudo ufw allow 8005/tcp
   sudo ufw allow 18080/tcp
   sudo ufw status
   ```

7. **Admin navigation update**
   * `src/ralph/admin/sitetrees.py` now exposes dedicated top-level menus for **Heavy Equipment**, **Fleet**, **Drones**, and **Sensors**. Legacy “Cloud”, “Networks”, “Licenses”, and “Intellectual Property” menus are hidden but the underlying apps remain available if needed later.
   * After modifying the sitetree (or pulling updates), run `make up` or manually execute `ralph sitetree_resync_apps` inside the `assets-web` container so cached menus stay in sync.

8. **SC3 integration notes**
   * Proxy `/assets/` on SC3’s nginx to the Ralph nginx container (map host port **18080** to container `80`, or wire it through an internal network-only route)
   * Use `make up` / `make logs` to rebuild and collect logs before packaging for SC3. The `DB_WAIT_*` knobs in the Makefile control how long we wait for MySQL before failing the build.
   * Give each service unique names (`assets-web`, `assets-db`, …) inside the SC3 compose file (the local compose already adopts these names to avoid collisions)
   * Mount dedicated volumes for MySQL data and media/static
   * Add simple HTTP health checks (`/login/`, `/admin/`) so SC3 waits for the service
   * Configure `RALPH_URL=http://assets-web:8005` and `VITE_ASSETS_URL=http://localhost:8005/assets`
9. **Background workers & schedulers**
   * Lifecycle automation (maintenance scheduling, compliance reminders, budget watchdog) runs from `django-rq`. Ensure `rq-scheduler` is installed in the virtualenv, then keep both a worker **and** the scheduler process online:
     ```bash
     docker compose -f docker/docker-compose-local-dev.yml exec assets-web venv/bin/python manage.py rqworker default
     docker compose -f docker/docker-compose-local-dev.yml exec assets-web venv/bin/python manage.py rqscheduler --queue default
     ```
   * Tweak intervals via `ASSETS_SCHEDULER_MAINTENANCE_INTERVAL`, `ASSETS_SCHEDULER_COMPLIANCE_INTERVAL`, `ASSETS_SCHEDULER_BUDGET_INTERVAL`, and `ASSETS_SCHEDULER_INVENTORY_INTERVAL` (seconds). Set `ASSETS_SCHEDULER_ENABLED=0` locally if you want to disable automatic scheduling.
   * Optional: `ASSETS_SCHEDULER_DIGEST_INTERVAL`, `ASSETS_SCHEDULER_SLA_INTERVAL`, `ASSETS_SCHEDULER_FORECAST_INTERVAL` control the cadence for new reporting/optimization jobs. `ASSETS_INTEGRATION_QUEUE` lets you target a dedicated RQ queue for outbound integrations.
10. **Integration endpoints**
    * Configure outbound hooks under **Assets → Integration endpoints** in the admin. Supported types today are webhooks/n8n/ERP (HTTP POST) and Celery tasks.
    * Use the optional secret token or custom headers for downstream verification. Provide a JSON list in `event_filter` to limit events (e.g. `"maintenance.started"`).
    * Delivery attempts are tracked in **Integration delivery logs**. Combine with `ASSETS_INTEGRATION_QUEUE` to isolate high-volume traffic.

## Live demo:

http://ralph-demo.allegro.tech/

* login: ralph
* password: ralph

## Screenshots

![img](https://github.com/allegro/ralph/blob/ng/docs/img/welcome-screen-1.png?raw=true)

![img](https://github.com/allegro/ralph/blob/ng/docs/img/welcome-screen-2.png?raw=true)

![img](https://github.com/allegro/ralph/blob/ng/docs/img/welcome-screen-3.png?raw=true)


## Documentation
Visit our documentation on [readthedocs.org](https://ralph-ng.readthedocs.org)

## Getting help

* Online forum for Ralph community: https://ralph.discourse.group


## New in sirius-ralph (2025 Q3–Q4)

This branch adds a broad set of asset-management and reporting capabilities on top of upstream Ralph:

- Asset taxonomy and admin navigation
  - Heavy Equipment constrained to classic machinery; new top-level sections for Trailers and Power & Lighting.
  - Submenus for subtypes (e.g., Command/Office/Restroom trailers; Generators/Light Towers/Battery Packs/Pumps) open filtered lists; edit forms hide fixed type/subtype fields.

- Lifecycle & operations
  - Work orders (WorkOrder + WorkOrderTask) sit alongside MaintenanceRecord for vendor/SLA approvals and costs.
  - Heavy Equipment operations tab shows Work Orders inline; other families can adopt the same inline.

- Telemetry & utilization adapters
  - Utilization endpoints now include availability-based KPIs when telemetry is absent (Data Center / Back Office). Each asset reports availability_rate; summaries add average_availability_rate.

- Reporting & dashboards
  - REST endpoints at `/api/reporting/`: `inventory`, `utilization`, `maintenance-compliance`, `lifecycle`, `financial`, `resources`.
  - Role dashboards: `dashboard/operations`, `dashboard/compliance`, `dashboard/finance`.
  - CSV export via `?format=csv` supported where applicable.

- Saved report configs & scheduling
  - Admin → Assets → Saved report configurations; schedule automatic emails by setting `schedule_interval_seconds`.
  - Command: `python manage.py run_report_config <id>`; `--dry-run` to preview.
  - RQ scheduler auto-registers active configs on service start.

- Snapshots & performance
  - Daily/Monthly ETL: `snapshot_asset_status_daily`, `snapshot_compliance_daily`, `snapshot_asset_costs_monthly`.
  - Snapshot models: `AssetStatusSnapshot`, `ComplianceSnapshot`, `AssetCostSnapshot`.
  - DB indexes added on maintenance/compliance/utilization/telemetry to accelerate reporting.

- Compliance risk & ownership
  - `ComplianceTemplate` includes severity (low→critical), owner user/team, and required document count.
  - Daily compliance snapshot emits a simple risk score based on status + severity + missing evidence.

### After pulling updates – migrations & jobs

Run the following inside the web container after pulling this branch:

```bash
PYTHONPATH=src DJANGO_SETTINGS_MODULE=ralph.settings.prod venv/bin/python -m django migrate

# optional: generate initial snapshots
venv/bin/python -m django snapshot_asset_status_daily
venv/bin/python -m django snapshot_compliance_daily
venv/bin/python -m django snapshot_asset_costs_monthly

# optional: create and run a report config
# (Create a ReportConfig in admin first and note its ID)
venv/bin/python -m django run_report_config <id> --dry-run
```

Keep an RQ worker and scheduler running for automation (see Background workers & schedulers above).

---

## Using the new asset families

Admin navigation (top navbar) exposes these families and their logs:

- Heavy Equipment: classic machinery (excavators, dozers, cranes, forklifts, etc.).
- Trailers: command, office, restroom, shower, laundry, sleeping quarters, medical, comms/fiber, water tank, storage, specialty.
- Power & Lighting: generators, light towers, battery/solar packs, pumps/aux power.
- Fleet, Drones, Sensors: vehicles, UAS, and IoT devices.

Each family has four pre-filtered log pages:

- Assignments (DeploymentEntry): where and with whom an asset is deployed, including shift rosters.
- Usage Logs (TelemetryReading): runtime hours, odometer, fuel/levels, occupancy, etc.
- Maintenance Logs (MaintenanceRecord/WorkOrder): open/closed work, SLA due dates, costs, parts.
- Status Logs (AssetIncident): incidents with tasks and attachments.

Quick start (Admin):

1) Create or select an Asset Model, Service/Environment, and Budget as needed (Settings → Asset model/Service/etc.).
2) Add an asset from the family’s “All …” menu, fill common fields (model, service, location) and family-specific fields (e.g., generator kW, trailer subtype).
3) Operate the asset via Transitions (on the asset detail): Assign/Deploy, Start/Complete Maintenance, Refuel/Replenish, Retire/Dispose. Transitions log maintenance and status changes automatically.
4) View Operations, Compliance, and Telemetry tabs on the asset detail to see recent actions, inspections, documents, and metrics.
5) Log parts usage from MaintenanceRecord (inline) — stock auto-decrements and restock alerts can be raised.

Notes

- Operator certifications and digital checklists (DVIR/pre-flight/safety) can gate transitions; expired credentials block assignment until renewed.
- Work Orders complement MaintenanceRecord when vendor approvals, SLAs, and sub-tasks are required.

---

## Reporting suite (cross-asset)

Endpoints under `/api/reporting/` power dashboards and exports:

- Inventory: portfolio by family, subtype, location, status.
- Utilization/Downtime: runtime/availability, idle time, MTBF/MTTR, time-in-state.
- Maintenance/Compliance: due/overdue work, risk score (status + severity + docs), costs.
- Financial/Budget: capex vs opex, cost history, cost-per-hour, budgets and overruns.
- Lifecycle/Disposal: retirements, disposal evidence completion.
- Resources (water/fuel): consumption/supply and anomalies across families.

Usage

- Filter by `?family=heavy_equipment|trailers|power|fleet|drones|sensors` plus `?location=…&service=…&date_from=…&date_to=…`.
- CSV export: append `?format=csv`.
- Saved report configs: Admin → Assets → Saved report configurations. Scheduler emails results on cadence (see below).

Legacy “Reports” pages updated

The built-in admin report pages now include the new asset families in their filter bar:

- Category model, Category model status, Manufacturer category model, Status model
- Asset relations, Licence relations, Assets supports, Failures

Switch the mode on each report to: Data Center, Back Office, Heavy Equipment, Trailers, Power & Lighting, Fleet, Drones, or Sensors as needed. Licensed software still primarily targets Back Office/Data Center; for other families, licence relations will list only universal (“all”) software.

---

## API and SC3 integration

Base URL examples (authenticated via DRF token or session):

- Assets (family lists):
  - `/api/heavy-equipment/assets/`, `/api/trailers/assets/`, `/api/power/assets/`
  - `/api/fleet/assets/`, `/api/drones/assets/`, `/api/sensors/assets/`

- Telemetry ingest (JSON):
  - `/api/telemetry/ingest/` — accepts `base_object`, `metric`, `value_numeric|value_text`, `captured_at`, and optional payload/units.

- Reporting:
  - `/api/reporting/inventory/`, `/api/reporting/utilization/`, `/api/reporting/maintenance-compliance/`, `/api/reporting/financial/`, `/api/reporting/lifecycle/`, `/api/reporting/resources/`

Integration patterns with SC3

1) Pull: SC3 dashboards call reporting endpoints on demand (JSON/CSV), scoped by project/location/family. Recommended for BI and in-app widgets.
2) Push (webhooks/queues): Configure Admin → Assets → Integration Endpoints to deliver `AssetEventType` notifications (maintenance opened/closed, compliance due/overdue, status change, budget overrun) to SC3’s n8n/Celery endpoints or queues.
3) Schedules: RQ-scheduler (or Celery beat) runs health checks and digests and can POST summaries to SC3 via Integration Endpoints.

Security

- Use DRF token auth or network isolation between Sirius and SC3. For webhooks, set shared secrets in Integration Endpoints and verify signatures in SC3 workflows.

---

## Background workers & schedulers

Install and run workers for maintenance/compliance/budget/inventory jobs:

```bash
venv/bin/pip install rq-scheduler

# one terminal: worker
PYTHONPATH=src DJANGO_SETTINGS_MODULE=ralph.settings.prod venv/bin/python -m django rqworker default

# another terminal: scheduler
PYTHONPATH=src DJANGO_SETTINGS_MODULE=ralph.settings.prod venv/bin/python -m django rqscheduler --queue default
```

Jobs (management commands)

- `schedule_maintenance`, `check_sla`, `check_compliance`, `check_inventory`, `check_asset_budgets`
- `snapshot_asset_status_daily`, `snapshot_compliance_daily`, `snapshot_asset_costs_monthly`
- `send_asset_digest`, `run_report_config`, `ingest_telemetry`

---

## Migrations and navigation

Apply migrations and refresh the admin menu:

```bash
PYTHONPATH=src DJANGO_SETTINGS_MODULE=ralph.settings.prod venv/bin/python -m django migrate
PYTHONPATH=src DJANGO_SETTINGS_MODULE=ralph.settings.prod venv/bin/python -m django sitetree_resync_apps
```

If the sitetree resync errors on DB connection, ensure your DB container is up and configured per environment settings, then rerun.

---

## Known gaps & next steps

- Legacy “Reports” pages (Category/Manufacturer/Status, Asset/Licence relations, Assets supports, Failures) don’t include the new families. Prefer the new reporting APIs and dashboards. We’ll either extend or deprecate legacy pages in a future pass.
- Ensure media storage is configured for document uploads (compliance/disposal/incident attachments) in production.
- Secure telemetry ingest and integration endpoints (auth/signatures, rate limits) before exposing externally.
- Optional: Celery/Redis alternative to RQ if you standardize on Celery in SC3.

---

## Branding note

This distribution uses the “Sirius Asset Manager” name and navigation, while acknowledging and building on upstream Ralph. Where the UI or code references the upstream project, consider it a technical provenance rather than end-user branding.
