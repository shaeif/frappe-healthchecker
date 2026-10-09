# HC Tracker – Frappe v16 app + Docker Compose

Tracks periodic network health checks (HC) for Cisco switches and WLCs, Palo Alto and FortiGate
firewalls. Each client has its own HC frequency (Monthly / Quarterly / Half-yearly / Yearly). A **notification
flow you can edit in the UI** decides who is notified, in what order, when, and how. Channels are Office 365 email,
a Microsoft Teams Adaptive Card and an **on-screen pop-up + bell notification**.

* Frappe Framework **v16** (tested on 16.50.0, Python 3.14), MariaDB 11.8, Redis 6.2
* Image built `FROM frappe/erpnext:v16`. The site installs **only `frappe` + `hc_tracker`**; ERPNext is not installed.
* Time zone **Asia/Qatar**. The daily job runs at **08:00** Qatar time.
* **Helpdesk scheduling and notification tool only.** HC Tracker never connects to client devices and stores no
  device credentials. Engineers run the health check with their own tools and attach the report.
* **v1.3 helpdesk features** (section 13): booking calendar with drag-and-drop, booking-request emails to the client,
  contact log with follow-ups, engineer leave / Qatar holidays / weekend (Fri-Sat) awareness, reschedule history with
  reasons, client visit reminders, a daily helpdesk to-do email, a weekly/monthly management summary, performance
  charts, Excel import, an audit trail report and Arabic / bilingual notifications plus an Arabic UI.

Other documents:

* [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md): step-by-step test plan with sample data for all four frequencies
* [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md): common errors and fixes

---

## 1. Clarifying questions (answered before building)

| Question | Answer used |
|---|---|
| Who receives step 1 (Helpdesk)? | Every enabled user with role **HC Helpdesk** (Role recipient). The shared mailbox in HC Settings is used only when a step targets the contract field `helpdesk_contact` and it is empty. |
| Frequency-specific day values | **5 flows** are created: `Standard HC Escalation` (default, applies to All, Quarterly values) plus one flow per frequency with matching days. A contract automatically uses the flow for its frequency. |
| Teams target | One channel, through **HC Settings > Default Teams Webhook URL**. A step may override it. |
| Pop-ups (later request) | Every email step can **also show an on-screen pop-up and a bell notification** to recipients who are system users (step checkbox *Also Show Pop-up*, master switch in HC Settings). The channel **System Notification** sends a pop-up only. |

Two small additions to the spec:

* Trigger mode **"Days before scheduled date"** was added, because the engineer reminder fires 3 days before
  `scheduled_date`, not before the due date.
* The default flow's step 2 is split into two rows: **2 = "HC booked"** (on status *Scheduled*) and
  **3 = "prep reminder"** (3 days before `scheduled_date`). The default flow therefore has these steps:
  1 Helpdesk · 2 Engineer booked · 3 Engineer prep · 4 Technical Manager · 5 Overdue · 6 Report sent ·
  7 Helpdesk follow-up (example of *Days after previous step*, **disabled** by default).

---

## 2. Project tree

```
frappe-healthchecker/
├── .dockerignore
├── .env.example                 # copy to .env (all passwords / site name live here)
├── .gitignore
├── Dockerfile                   # FROM frappe/erpnext:v16 + apps/hc_tracker (pip install -e)
├── apps.json.example            # for the official "layered" image build (production path)
├── docker-compose.yml           # pwd.yml layout: backend, configurator, create-site, db, frontend,
│                                #   queue-short, queue-long, redis-cache, redis-queue, scheduler, websocket
├── docs/
│   ├── TEST_PLAN.md
│   └── TROUBLESHOOTING.md
├── scripts/
│   ├── backup.sh                # bench backup --with-files + copy to ./backups
│   └── restore.sh               # restore a backup set from ./backups
└── apps/
    └── hc_tracker/
        ├── .gitignore
        ├── README.md
        ├── license.txt
        ├── pyproject.toml       # flit_core, requires-python >=3.14
        └── hc_tracker/
            ├── __init__.py      # __version__
            ├── hooks.py         # install hooks, permissions, cron 08:00, popup JS
            ├── modules.txt      # "HC Tracker"
            ├── patches.txt
            ├── permissions.py   # permission_query_conditions + has_permission
            ├── utils.py
            ├── scheduling.py    # working days, Qatar holidays, engineer availability checks
            ├── api/
            │   ├── booking.py        # booking-request email to the client (+ contact log)
            │   ├── calendar.py       # Booking Calendar events + drag-and-drop booking / rescheduling
            │   ├── import_tools.py   # Excel import template download
            │   ├── metrics.py        # workspace performance charts
            │   ├── number_cards.py   # workspace number cards (permission aware)
            │   ├── queries.py        # "users with role X" link query
            │   └── tools.py          # test email / Teams card / pop-up buttons
            ├── config/__init__.py
            ├── notifications/
            │   ├── channels.py       # Email, Teams Adaptive Card, System Notification (bell + pop-up)
            │   ├── engine.py         # step evaluation, recipients, sending, log, dry run, timeline
            │   ├── helpdesk_todo.py  # daily helpdesk to-do email
            │   ├── scheduler.py      # daily job, overdue digest, renewal alerts
            │   ├── summary.py        # weekly / monthly management summary
            │   └── templates.py      # default Jinja subjects/messages (English + Arabic)
            ├── public/
            │   ├── images/hc_tracker_logo.svg
            │   └── js/hc_tracker_popup.js   # real-time pop-up listener (plain JS, no build)
            ├── patches/v1_2/remove_device_data_collection.py   # cleans up the removed collection feature
            ├── patches/v1_3/helpdesk_features.py               # v1.3 settings, flow steps, cycle backfill, holidays
            ├── translations/ar.csv   # Arabic UI translations
            ├── setup/
            │   ├── default_flows.py  # Standard HC Escalation (+4 frequency copies)
            │   ├── demo.py           # sample users + contracts for the test plan
            │   └── install.py        # roles, time zone, settings, flows
            └── hc_tracker/           # module "HC Tracker"
                ├── doctype/
                │   ├── hc_contract/            (.json .py .js _list.js _calendar.js test_)
                │   ├── hc_contact_log/         (calls / emails with the client, follow-ups)
                │   ├── hc_cycle/               (child: history)
                │   ├── hc_engineer_leave/      (engineer unavailability)
                │   ├── hc_holiday/             (public holidays; Qatar defaults seeded)
                │   ├── hc_notification_flow/   (.json .py .js _list.js test_)
                │   ├── hc_notification_step/   (child: one row per escalation step)
                │   ├── hc_notification_log/    (.json .py .js _list.js)
                │   ├── hc_reschedule/          (child: reschedule history)
                │   └── hc_settings/            (single)
                ├── dashboard_chart/         (Completed per Month, On-time vs Late, Avg Days Due to Sign-off, Due per Month)
                ├── dashboard_chart_source/hc_tracker_metrics/
                ├── number_card/   (Due This Month, Overdue, Awaiting Sign-off, Notifications Failed Today,
                │                   Follow-ups Due Today)
                ├── report/
                │   ├── upcoming_health_checks/   (Script Report)
                │   ├── helpdesk_to_do/           (Script Report)
                │   ├── hc_management_summary/    (Script Report + chart)
                │   └── hc_audit_trail/           (Script Report, from document versions)
                ├── sidebar/hc_tracker/              (v16 sidebar)
                └── workspace/hc_tracker/            (workspace with shortcuts, number cards + charts)
```

---

## 3. How it works (short)

* **HC Contract** (named by `client_id`): `interval_months` comes from the frequency. Attaching
  `current_report` moves the status to *Report sent*. Only **HC Account Manager / HC Technical Manager / System Manager**
  can set *Signed off*, and only when a report is attached. Sign-off does the following:
  1. appends an **HC Cycle** history row;
  2. sets `last_hc_date` to `scheduled_date`, or today when it is empty;
  3. rolls `next_due_date` forward by `interval_months` **from the previous due date**;
  4. clears the current-cycle fields and sets the status back to *Not started*.

  A new cycle label (`2026-10`, `2026-Q4`, `2026-H2`, `2026`) starts a fresh set of steps.
* **Notification engine**: one function evaluates every step. The daily job, the status-change hook, the
  **Test Flow** dry run and the contract's **Notification Timeline** all call it. Each step is checked for:
  * when it should fire;
  * whether `only_if_status_in` and `stop_when_status` allow it;
  * who it goes to, with fallbacks;
  * which channels apply.

  De-duplication uses **HC Notification Log**, one row per *(contract, flow, cycle, step, channel)*. The check is
  `planned_date <= today` (never an exact-day match), so a skipped run is caught up the next day. A second run on the
  same day sends nothing. A *Failed* channel (e.g. Teams down) is retried on the next run without resending
  the channels that already worked. `repeat_every_days` re-sends while the conditions still hold.
* **Recipients**: *Contract Field* `technical_manager` falls back to *HC Settings > Default Technical Manager*,
  and `helpdesk_contact` falls back to *Default Helpdesk Email*. After that, the step's *Fallback Role* applies.
* **Pop-ups**: for each system user among the recipients, a Notification Log ("Alert" type, never emailed
  twice) is created and a real-time event `hc_tracker_popup` is pushed. `hc_tracker_popup.js` (loaded on every desk page)
  shows a dialog with an **Open Contract** button and an optional browser desktop notification. Users who were offline
  still find the message under the bell.
* **Working days**: Friday and Saturday are the weekend by default, and **HC Holiday** holds public holidays
  (Qatar National Day 18 Dec and National Sport Day are seeded; add the Eid dates each year). When *Skip Weekends and
  Holidays* is on, the daily job does nothing on a non-working day, and a step that would fall on one is moved: "before"
  reminders to the previous working day, all others to the next. A skipped day is still caught up.
* **Reschedules**: changing a booked *Scheduled Date* asks for a *Reschedule Reason* (and an optional note). A row
  is added to *Reschedule History*, the engineer gets step 8 *HC rescheduled* (CC helpdesk), and the "before scheduled
  date" reminders (prep, client visit reminder) are sent again for the new date.
* **Pausing**: *Reminders Paused Until* (set directly or from a contact log entry, e.g. "client asked for later date")
  holds back date-based reminders. Steps ticked *Ignore Pause* (the overdue escalation in the default flows) still fire.
* **Teams**: payload is `{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive",...}]}`
  (Adaptive Card 1.4). This is the format the Teams **Workflows** webhook expects, not the retired Office 365 connector
  `MessageCard`.

---

## 4. Install and run

### 4.1 Prerequisites
Docker Engine 23+ with the Compose v2 plugin, about 4 GB RAM, and internet access while building (pip fetches `flit_core`).

### 4.2 Configure
```bash
git clone <this repo> hc-tracker && cd hc-tracker
cp .env.example .env
nano .env            # set DB_ROOT_PASSWORD, ADMIN_PASSWORD, SITE_NAME, HOST_NAME
```
`SITE_NAME` **must be the hostname users type in the browser** (production: your FQDN, e.g. `hc.example.com`;
local test: `hc.localhost`). `HOST_NAME` is the full base URL used in email/Teams links,
e.g. `https://hc.example.com` or `http://hc.localhost:8080`.

### 4.3 Build and start
```bash
docker compose build                      # builds hc-tracker:latest FROM frappe/erpnext:v16
docker compose up -d                      # db/redis -> configurator -> create-site -> backend/frontend/workers
docker compose logs -f create-site        # wait for "Site <SITE_NAME> ready", then Ctrl+C
docker compose ps                         # backend/frontend (healthy), create-site/configurator Exited (0)
```
Open **http://hc.localhost:8080** (or your `SITE_NAME`) and log in as `Administrator` with `ADMIN_PASSWORD`.

On first login a frappe-only site shows the **setup wizard**. Complete it (any time zone you pick is reset
to Asia/Qatar afterwards). Or skip it from the CLI:
```bash
docker compose exec backend bench --site hc.localhost execute \
  frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
  --kwargs '{"args": {"language": "English", "country": "Qatar", "timezone": "Asia/Qatar", "currency": "QAR"}}'
```

### 4.4 Everyday commands
```bash
docker compose logs -f backend scheduler queue-short queue-long   # logs
docker compose logs --tail=200 websocket frontend
docker compose ps
docker compose stop        # stop (data kept)
docker compose start
docker compose down        # remove containers (named volumes db-data, sites, logs are kept)
docker compose exec backend bash                                  # shell inside the bench
docker compose exec backend bench --site hc.localhost console     # Python console
docker compose exec backend bench --site hc.localhost doctor      # scheduler / workers status
```
> In every command below replace `hc.localhost` with your `SITE_NAME`.

---

## 5. Users and roles

Roles created on install: **HC Helpdesk, HC Engineer, HC Account Manager, HC Technical Manager**.

```bash
S=hc.localhost
docker compose exec backend bench --site $S add-user helpdesk@company.qa --first-name Hana --last-name Helpdesk \
  --user-type "System User" --add-role "HC Helpdesk" --password 'Choose-A-Strong-One'
docker compose exec backend bench --site $S add-user omar@company.qa --first-name Omar --last-name Engineer \
  --user-type "System User" --add-role "HC Engineer" --password 'Choose-A-Strong-One'
docker compose exec backend bench --site $S add-user ali@company.qa --first-name Ali --last-name AM \
  --user-type "System User" --add-role "HC Account Manager" --password 'Choose-A-Strong-One'
docker compose exec backend bench --site $S add-user tariq@company.qa --first-name Tariq --last-name TM \
  --user-type "System User" --add-role "HC Technical Manager" --password 'Choose-A-Strong-One'

# add roles to an existing user
docker compose exec backend bench --site $S execute hc_tracker.setup.install.add_roles \
  --kwargs '{"user": "omar@company.qa", "roles": "HC Engineer,HC Helpdesk"}'
```
UI alternative: **User > (user) > Roles**, tick the HC role, and save.

| Role | Contracts | Notification Flow / Settings |
|---|---|---|
| HC Helpdesk | read all; can only change **Status Not started → Scheduled** and **Scheduled Date** | read flows |
| HC Engineer | only contracts where they are **Assigned Engineer** (read/write) | read flows |
| HC Account Manager | only contracts where they are **Account Manager**; can create; **can sign off** | read flows |
| HC Technical Manager / System Manager | everything | **edit** flows and settings |

These rules are enforced by `permission_query_conditions` (lists, reports, number cards) and `has_permission`
(documents) in `hc_tracker/permissions.py`. The helpdesk field restriction is enforced in `HCContract.validate()`.

---

## 6. Office 365 Email Account (smtp.office365.com:587, STARTTLS)

UI: **Search bar > Email Account > + Add Email Account**

| Field | Value |
|---|---|
| Email Address | `hc-notify@company.qa` (licensed mailbox or shared mailbox with SMTP AUTH allowed) |
| Service | *(leave empty)* |
| Method | **Basic** (or **OAuth**, see below) |
| Password | mailbox password / app password |
| Enable Outgoing | ✔ |
| Outgoing Server | `smtp.office365.com` |
| Port | `587` |
| Use TLS | ✔ (STARTTLS on 587) · **Use SSL: off** |
| Default Outgoing | ✔ |
| Always use this email address as sender address | ✔ (Exchange rejects other senders) |
| Enable Incoming | off (not needed) |

Save. Frappe tests the SMTP login on save. Then click **HC Settings > Test > Send Test Email**.

Microsoft 365 prerequisites: *Authenticated SMTP* must be enabled for the mailbox
(Microsoft 365 admin > Users > Mail > Manage email apps), and the tenant must allow SMTP AUTH.

**If the tenant blocks Basic auth for SMTP** (error `535 5.7.139 Authentication unsuccessful, basic authentication
is disabled`), use OAuth:

1. In Entra ID, go to **App registrations > New**. Add a Web redirect URI, copied from the Frappe **Connected App**
   form's *Redirect URI* field (`https://<site>/api/method/frappe.integrations.doctype.connected_app.connected_app.callback`).
   Create a client secret. Add delegated permissions `SMTP.Send` (Office 365 Exchange Online), `offline_access`,
   `openid` and `email`.
2. In Frappe, create a **Connected App** with:
   * Client Id / Secret from the app registration;
   * Authorization URI `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize`;
   * Token URI `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token`;
   * Scopes `https://outlook.office.com/SMTP.Send` and `offline_access`.
3. In the Email Account, set **Method = OAuth**, pick the Connected App, and click **Authorize API Access**
   while logged in to Microsoft as the mailbox.

Emails go through the **Email Queue** (sent by the `queue-short` / `queue-long` workers). See
*Troubleshooting* if they stay *Not Sent*.

---

## 7. HC Settings

**Search bar > HC Settings** (Technical Manager / System Manager only):

| Field | Meaning |
|---|---|
| Default Helpdesk Email | shared mailbox; fallback for steps targeting `helpdesk_contact` |
| Default Technical Manager | fallback for steps targeting `technical_manager`; always receives the digest |
| Enable Daily Overdue Digest / Digest Recipients | HTML table of all overdue contracts (email + Teams) every morning |
| Renewal Alert Days (60) | Account Manager alert this many days before `contract_end` |
| Enable Teams / Default Teams Webhook URL | Teams Workflows webhook (see below) |
| Enable Pop-up Notifications | on-screen pop-up + bell for system-user recipients |
| Weekend Days (`Friday,Saturday`) | non-working weekdays, comma separated |
| Skip Weekends and Holidays (on) | no daily run on weekends / HC Holidays; reminders move to working days |
| Block Unavailable Bookings (off) | off: warn when booking on leave / a holiday / a double booking; on: refuse the save |
| Booking Request Subject / Message | optional Jinja override of the booking-request email |
| Enable Helpdesk To-Do (on) | daily to-do email + pop-up to HC Helpdesk users |
| Book-Now Horizon (45 days) | unbooked contracts due within this many days appear under *Book now* |
| Client Reply Wait (3 days) | after a booking request, the contract moves to *Awaiting client reply* after this many days |
| Summary Frequency (Weekly) / Summary Recipients | management summary: Weekly (Sunday, previous 7 days), Monthly (1st, previous month) or Off. Technical Managers always receive it |
| Notification Language (English) | English, Arabic or English + Arabic (bilingual) emails, digests and to-do lists |

Buttons under **Test**: *Send Test Email*, *Send Test Teams Card*, *Send Test Pop-up To Me*, *Run Daily Job Now*,
*Send Helpdesk To-Do Now*, *Send Management Summary Now*.

**Teams Workflows webhook**: in the Teams channel, open **… > Workflows > "Post to a channel when a webhook request is
received"**. Pick the team and channel, then copy the generated URL into *Default Teams Webhook URL*. If you build
the flow yourself in Power Automate, use the trigger *When a Teams webhook request is received* and the action
*Post card in a chat or channel* with *Adaptive Card* = `attachments[0].content`.

CLI alternative:
```bash
docker compose exec backend bench --site hc.localhost console
>>> s = frappe.get_single("HC Settings")
>>> s.default_technical_manager = "tariq@company.qa"
>>> s.digest_recipients = "noc@company.qa, tariq@company.qa"
>>> s.enable_teams = 1; s.default_teams_webhook_url = "https://prod-00.westeurope.logic.azure.com/workflows/..."
>>> s.save(); frappe.db.commit()
```

---

## 8. Editing the notification flow (no code)

**HC Notification Flow** list: `Standard HC Escalation` (default, All) and `… - Monthly / Quarterly / Half-yearly / Yearly`.

Open a flow and edit the **Escalation Steps** table (click a row's edit icon for all fields):

* **Step No / Label / Enabled**
* **Recipient**:
  * *Contract Field* (`assigned_engineer`, `account_manager`, `helpdesk_contact`, `technical_manager`);
  * *Role* (all enabled users with the role);
  * *Specific User*;
  * *Email Address* (one or more, comma separated);
  * *Client Contact* (the contract's *Client Contact Email* + *Client CC Emails*).

  Plus an optional **Fallback Role** and a **CC** of the same types.
* **When**: *Days before due date*, *Days after due date (overdue)*, *Days before scheduled date*,
  *Days after previous step if not resolved* (+ *After Step No*), *On status change* (+ *On Status*), or
  *On reschedule*. These are combined with *Trigger Days*, *Only If Status In*, *Stop When Status*,
  *Repeat Every (days)* and *Ignore Pause*.
* **How**: *Channel* (Email, Teams, Email + Teams, System Notification), *Also Show Pop-up*, and an optional per-step
  *Teams Webhook URL*.
* **Message**: Jinja *Subject Template* / *Message Template*. Leave them empty to use the defaults. Variables are
  `doc`, `step`, `flow`, `days_left`, `days_overdue`, `due_date`, `scheduled_date`, `days_to_scheduled`,
  `contract_url`, `cycle_label`, `today`, `event_status` and `last_cycle` (plus `old_scheduled_date`,
  `reschedule_reason` and `reschedule_note` for *On reschedule* steps). *Subject / Message Template (Arabic)* are used
  when *Notification Language* is Arabic or English + Arabic.

Default steps in every flow: 1 Helpdesk, 2 Assigned Engineer - HC booked, 3 Assigned Engineer - prep reminder,
4 Technical Manager, 5 Overdue escalation, 6 Report sent - Account Manager, 7 Helpdesk follow-up (not booked), and
since v1.3 **8 Assigned Engineer - HC rescheduled** (On reschedule, CC helpdesk) and **9 Client - visit reminder**
(Client Contact, 1 day before the booked date for Monthly and 2 days for the others, CC helpdesk). Upgrading adds
steps 8 and 9 and the Arabic templates to the standard flows; flows you created yourself are not changed.

Save, then click **Test Flow**. Pick a contract and a date to see which steps would fire, to whom, on which
channels, and the rendered subject. Nothing is sent or logged. You can tick **Is Default** on another flow (only one
default is allowed), and you can pin a specific flow on a contract (*Notification Flow* field).

---

## 9. Daily job

* Cron `0 8 * * *` → `hc_tracker.notifications.scheduler.run_daily`, evaluated in System Settings time zone (Asia/Qatar).
* It runs, in order:
  1. every open contract's flow;
  2. the overdue digest;
  3. contract renewal alerts;
  4. the helpdesk to-do email;
  5. the management summary (only on its day: Sunday for Weekly, the 1st for Monthly).

  On a weekend day or HC Holiday (with *Skip Weekends and Holidays* on) only the management summary is checked.

  Each part commits separately, and errors go to **Error Log**.

```bash
# run it now
docker compose exec backend bench --site hc.localhost execute hc_tracker.notifications.scheduler.run_daily
# simulate a date (logs are stored with that run_date)
docker compose exec backend bench --site hc.localhost execute hc_tracker.notifications.scheduler.run_daily \
  --kwargs '{"on_date": "2026-11-01"}'
# scheduler state
docker compose exec backend bench --site hc.localhost scheduler status
docker compose exec backend bench --site hc.localhost scheduler enable
docker compose exec backend bench --site hc.localhost scheduler resume
```

---

## 10. Update the app after code changes

```bash
git pull                                   # or edit apps/hc_tracker/...
docker compose build                       # rebuild hc-tracker:latest
docker compose up -d                       # recreate containers with the new image
docker compose exec backend bench --site hc.localhost migrate
docker compose exec backend bench --site hc.localhost clear-cache
```
* Always run `migrate` after changing DocType JSON, hooks (cron, permissions), workspace, number cards or patches.
* If you edit a DocType / workspace / sidebar **JSON by hand**, bump its `"modified"` timestamp. Otherwise
  `migrate` treats the file as unchanged and skips it.
* Static files are served from the image, so `docker compose up -d` is enough. Never run `bench build` inside a
  running container.
* Bump `__version__` in `hc_tracker/__init__.py` for releases.

### Production path: official "layered" image + `apps.json`
Put `apps/hc_tracker` in its own Git repository (the folder `apps/hc_tracker` becomes the repo root), then:
```bash
git clone https://github.com/frappe/frappe_docker && cd frappe_docker
cat > apps.json <<'JSON'
[ { "url": "https://github.com/YOUR-ORG/hc_tracker", "branch": "main" } ]
JSON
# private repo: "url": "https://<token>@github.com/YOUR-ORG/hc_tracker"  (passed as a BuildKit secret, never stored in layers)
docker build --no-cache \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-16 \
  --secret=id=apps_json,src=apps.json \
  --tag=hc-tracker:1.0.0 \
  --file=images/layered/Containerfile .
```
Then set `CUSTOM_IMAGE=hc-tracker` and `CUSTOM_TAG=1.0.0` in this repo's `.env`, and run `docker compose up -d` +
`bench migrate`. You can drop the `build:` section, or build in CI and push to your registry. The layered image builds
assets with `bench build` and contains only the apps listed (plus frappe). Pin `BASE_TAG` (e.g. `v16.50.0`) for
reproducible builds of the simple Dockerfile.

For HTTPS in production, put a reverse proxy (Traefik/Caddy/nginx) in front of port 8080. Set `SITE_NAME` to the FQDN
and `HOST_NAME=https://<FQDN>`. The websocket container must be able to reach `https://<FQDN>` (normal DNS).

---

## 11. Backup and restore

```bash
./scripts/backup.sh                      # DB + public/private files + site config -> ./backups
./scripts/restore.sh 20261009_183250     # restore a backup set by its timestamp prefix
```
Manual equivalent:
```bash
docker compose exec backend bench --site hc.localhost backup --with-files
docker compose cp backend:/home/frappe/frappe-bench/sites/hc.localhost/private/backups/. ./backups/

docker compose cp ./backups/. backend:/tmp/restore/
docker compose exec backend bench --site hc.localhost restore /tmp/restore/<ts>-hc_localhost-database.sql.gz \
  --with-public-files /tmp/restore/<ts>-hc_localhost-files.tar \
  --with-private-files /tmp/restore/<ts>-hc_localhost-private-files.tar \
  --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" --force
docker compose exec backend bench --site hc.localhost migrate
```
Also back up `.env` (the encryption key is in `sites/<site>/site_config.json`, which is in the `sites` volume and in
`*-site_config_backup.json`. You need it to restore encrypted Password fields, such as the Email Account password).
Volume-level backup: `docker run --rm -v hc-tracker_sites:/v -v $PWD/backups:/b alpine tar czf /b/sites.tgz -C /v .`

---

---

## 12. Scope: no device data collection

HC Tracker is a **helpdesk tool**: it tracks contracts, due dates, bookings, reports and sign-offs, and sends the
notifications. It does **not** connect to client devices, run commands or store device credentials. Engineers
collect data with their own tools and attach the HC report on the contract's *Current Cycle* tab.

An earlier build (v1.1) had an optional device-collection feature. Upgrading to v1.2 with `bench migrate` runs
the patch `hc_tracker.patches.v1_2.remove_device_data_collection`, which deletes:
* the collection runs, their draft PDFs and raw-output ZIPs;
* the contract Devices table, including the encrypted device credentials;
* the related settings.

Reports already attached to contracts are kept.

---

## 13. Helpdesk features (v1.3)

Everything below is on the **HC Contract** form under the **Helpdesk** button group, on the contract list, or in the
**HC Tracker** workspace. Upgrading an existing site is just `bench migrate` (section 10); the patch
`hc_tracker.patches.v1_3.helpdesk_features` sets the new defaults, adds steps 8 and 9 to the standard flows, fills
the due date / sign-off date / days late on existing cycle rows, seeds the Qatar holidays and lets HC Helpdesk use
Data Import.

| Feature | Where | What it does |
|---|---|---|
| **Booking Calendar** | Contract list > *Booking Calendar*, workspace shortcut | Month / week / day view. Booked HCs show by *Scheduled Date* (blue), unbooked ones by *Next Due Date* ("Due: …"). Holidays are shaded; filter by engineer to also shade their leave. Drag a "Due" item to a day to **book** it (status → Scheduled); drag a booked item to **reschedule** it (reason "Changed in calendar"). |
| **Book / Reschedule dialog** | *Helpdesk > Book Health Check* (or *Reschedule*) | Pick a date and see, live, whether it is a weekend or holiday, whether the engineer is on leave, and the engineer's other bookings that week. Rescheduling asks for a reason and an optional note. |
| **Availability checks** | on save | Booking on a weekend, a holiday, an engineer's leave day or a day the engineer already has another HC shows a warning (or blocks the save with *Block Unavailable Bookings*). |
| **Engineer leave / holidays** | *HC Engineer Leave*, *HC Holiday* | Helpdesk and Technical Managers record leave and public holidays. Saving leave that overlaps already booked HCs lists them so they can be moved. |
| **Booking request email** | *Helpdesk > Send Booking Request* | Prefilled email to the client contact (CC the client CC list) with up to three proposed dates. It is sent from the Office 365 account, stored as a Communication on the contract timeline (with an incoming Email Account, client replies are linked to it), and logged in the contact log. |
| **Contact log + follow-ups** | *Helpdesk > Log Contact Attempt*, *Contact History*, *HC Contact Log* list | Record calls / emails / Teams / WhatsApp, the outcome, a follow-up date and an optional *pause reminders until*. A "date confirmed" outcome offers to book the HC straight away. Engineers cannot see contact logs of other engineers' clients. |
| **Client visit reminder** | flow step 9 | Email to the client contact 1–2 days before the booked visit, CC helpdesk. |
| **Reschedule history** | contract *Current Cycle* tab | Every date change with old date, new date, reason, note, who and when; the engineer is told (step 8). |
| **Helpdesk to-do** | daily email + pop-up, *Helpdesk To-Do* report | Five lists: follow-ups due today, awaiting client reply, book now, confirm with client (booked in the next 2 working days) and overdue, each with the client contact's name and phone. *HC Settings > Send Helpdesk To-Do Now* sends it on demand. |
| **Management summary** | weekly / monthly email, *HC Management Summary* report | Per client or per engineer: completed, on time, late, on-time %, average days from due date to sign-off, pending and overdue. Technical / Account Managers only. |
| **Performance charts** | workspace | Completed per month, on-time vs late and average days due → sign-off (last 12 months); due per month (overdue + next 12 months). Engineers see only their own contracts. |
| **Excel import** | Contract list > *Import > Download Excel Template* / *Import from Excel* | Template with the contract columns and a Help sheet; the import uses Frappe's Data Import, so errors are listed per row. Technical Managers (and System Managers) only. |
| **Audit trail** | *HC Audit Trail* report | Who changed status, dates, frequency, engineer / managers, report, flow, reminders pause or contract end, plus sign-offs and reschedules, from the document version history. Technical Managers only. |
| **Arabic** | user language, *Notification Language* | Users whose language is Arabic get the desk in Arabic (RTL) with all HC Tracker labels translated. Notifications can be English, Arabic or bilingual; each default step has an Arabic subject and message you can edit in the flow. |

Contract fields added for these features: *Client Contact Name / Email / Phone*, *Client CC Emails*,
*Preferred Contact Method*, *Reminders Paused Until*, *Reschedule Reason / Note* and the read-only
*Last Contact On / Outcome*, *Booking Request Sent On* and *Last Rescheduled On*.
