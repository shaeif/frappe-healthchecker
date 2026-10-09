# AMC Tracker – Frappe v16 app + Docker Compose

AMC Tracker manages **Annual Maintenance Contracts (AMCs)** and their periodic **preventive maintenance (PM)**:

* **Clients** and their **AMCs**. One client can have several AMCs, e.g. a Network AMC and a Security AMC.
* **Engineers by expertise.** Each AMC lists its engineers and their area of expertise (Routing & Switching,
  Wireless, Security / Firewall, Data Center, Collaboration, or anything you add).
* **The PM cycle** (Monthly / Quarterly / Half-yearly / Yearly):
  1. The **helpdesk assigns the engineers**.
  2. **Each engineer sets their own visit date** with the client, on-site or remote.
  3. Reports are submitted **per visit** or as **one combined report**.
  4. A manager **signs off** the cycle, and the next PM due date rolls forward.
* **Notifications you configure in the UI**: email (Office 365), Microsoft Teams and on-screen pop-ups, in
  English, Arabic or both.

Technical basics:

* Frappe Framework **v16** (Python 3.14), MariaDB 11.8, Redis. The image is built `FROM frappe/erpnext:v16`, but the
  site installs **only `frappe` + `amc_tracker`**.
* Time zone **Asia/Qatar**, weekend Friday–Saturday. The daily job runs at **08:00**.
* AMC Tracker never connects to client devices and stores no device credentials.

Other documents: [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) (step-by-step test with sample data) ·
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

---

## 1. Install (one command)

Docker Engine 23+ with the Compose v2 plugin, about 4 GB RAM:

```bash
git clone <this repo> amc-tracker && cd amc-tracker
./scripts/install.sh            # local test: http://amc.localhost:8080
./scripts/install.sh --demo     # + sample users (one per role), clients and AMCs T-001..T-006
./scripts/install.sh --site amc.example.com --url https://amc.example.com --port 80   # production names
```

The script:

* creates `.env` with random database and Administrator passwords (mode 600);
* builds the image and starts the stack;
* waits for the site and completes the setup wizard (Qatar, Asia/Qatar, QAR);
* prints the URL and how to log in.

Running it again is safe: the existing `.env` and site are kept. `--no-build` reuses the image already built.

Then set up the Office 365 email account (section 6) and **Settings** (section 7).

<details><summary>Manual install (same steps by hand)</summary>

```bash
cp .env.example .env && nano .env        # DB_ROOT_PASSWORD, ADMIN_PASSWORD, SITE_NAME, HOST_NAME
docker compose build                     # amc-tracker:latest FROM frappe/erpnext:v16
docker compose up -d                     # db/redis -> configurator -> create-site -> backend/frontend/workers
docker compose logs -f create-site       # wait for "Site <SITE_NAME> ready"
docker compose exec backend bench --site amc.localhost execute \
  frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
  --kwargs '{"args": {"language": "English", "country": "Qatar", "timezone": "Asia/Qatar", "currency": "QAR"}}'
```
</details>

* `SITE_NAME` **must be the hostname users type in the browser** (production: your FQDN; local: `amc.localhost`).
  If it isn't, real-time pop-ups fail.
* `HOST_NAME` is the base URL used in email and Teams links, e.g. `https://amc.example.com`.

Everyday commands:
```bash
docker compose ps | logs -f backend scheduler | stop | start
docker compose exec backend bench --site amc.localhost console     # Python console
docker compose exec backend bench --site amc.localhost doctor      # scheduler / workers status
```
(Replace `amc.localhost` with your `SITE_NAME` in every command.)

---

## 2. Data model

```
Client  (code, name, account manager, primary contact, CC emails)
 └── AMC  (AMC-2026-0001: PM frequency, contract period, account / technical manager, scope)
      ├── Engineers table: engineer + expertise (+ lead)   <- the helpdesk maintains this
      ├── current PM cycle: next due date, cycle status, combined report, client sign-off
      ├── PM Cycle history (one row per signed-off cycle)
      └── PM Visit  (PMV-2026-00001) one per engineer per cycle
           engineer, expertise covered, visit date + time, On-site / Remote,
           visit report (or "included in the combined AMC report"), reschedule history
Client Contact Log   calls / emails with the client, follow-up date, pause reminders
Engineer Leave · Public Holiday · Expertise · AMC Notification Rules / Log · AMC Settings
```

**Cycle status** is calculated from the visits; nobody types it in:

| Cycle status | When |
|---|---|
| Not started | no visits yet: the helpdesk must **Assign Engineers** |
| Engineers assigned | at least one visit has no date yet |
| Scheduled | every visit has a date |
| In progress | at least one visit is completed / reported |
| Reports submitted | every visit has its report (own report, or ticked "included in the combined report" with the combined report attached on the AMC) → ready for sign-off |
| Signed off | event only: the cycle is archived in PM History, the due date rolls forward from the previous due date, and the status returns to Not started |

**Visit status** is calculated too:

| Visit status | When |
|---|---|
| To be scheduled | the visit has no date yet |
| Scheduled | a date is set |
| Completed | *Mark Completed* was used |
| Report submitted | a visit report is attached, or the visit is in the combined report |
| Cancelled | set by the helpdesk; *Reopen* is available |

---

## 3. Who does what (roles)

Roles created on install: **AMC Helpdesk, AMC Engineer, AMC Account Manager, AMC Technical Manager**.

| | Helpdesk | Engineer | Account Manager | Technical Manager / System Manager |
|---|---|---|---|---|
| Clients | all; create / edit contacts | only clients of their AMCs (read) | all; create / edit | all |
| AMCs | all; **assign engineers**, pause reminders, notes | only AMCs they are on; attach combined report | all; create / edit; **sign off** | all; everything |
| PM Visits | all; create, cancel, reopen, reassign | see visits of their AMCs, **edit only their own** (date, mode, report) | all (read) | all |
| PM To-Do | ✔ (daily email + report) | – | ✔ | ✔ |
| Management Summary | – | – | ✔ | ✔ |
| Audit Trail, Settings, Notification Rules | – | – | – | ✔ |
| Engineer Leave | all | own leave | read | all |

The sidebar is **role-based**: everyone only sees what they can open.

* **Helpdesk:** Dashboard; Operations (Clients, AMCs, PM Visits, PM Calendar, PM To-Do, Contact Log); Reports
  (Upcoming PM).
* **Engineer:** *My Work* (my visits to schedule, my next visits, my reports pending, My Leave); Operations; Upcoming PM.
* **Managers:** additionally Management Summary, Audit Trail and **Settings**.

Notification rules, the notification log, engineer leave, public holidays and expertise are not on the sidebar.
They open from **Settings > Setup**.

Add users:
```bash
docker compose exec backend bench --site amc.localhost add-user omar@company.qa --first-name Omar --last-name Engineer \
  --user-type "System User" --add-role "AMC Engineer" --password 'Choose-A-Strong-One'
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.install.add_roles \
  --kwargs '{"user": "omar@company.qa", "roles": "AMC Engineer,AMC Helpdesk"}'
```
UI alternative: **Settings > Setup > Users > (user) > Roles**.

These rules are enforced by `permission_query_conditions` (lists, reports, cards) and `has_permission` (documents) in
`amc_tracker/permissions.py`. The field-level limits for the helpdesk and engineers are enforced in
`AMC.validate()` and `PMVisit.validate()`.

---

## 4. The PM workflow, step by step

1. **Set up the client and AMC** (Account / Technical Manager). Create the **Client** (contact, CC emails), then
   **New AMC**: PM frequency, next PM due date, contract period, and the **Engineers** table (engineer + expertise).
   Clients and AMCs can also be imported from Excel (section 9).
2. **Assign engineers** (Helpdesk). Rule 1 emails the helpdesk when it is time. On the AMC, open the
   **PM Cycle** tab > **Assign Engineers**:
   * The dialog lists the AMC's engineers. Remove, add or change rows and choose On-site / Remote.
   * One **PM Visit** is created per engineer. An engineer listed with two areas (e.g. Data Center + Collaboration)
     gets **one** visit covering both.
   * Each engineer is told to schedule their visit.
3. **Engineer sets the date.** From *My Work* or the email link, open the PM Visit and click **Set Visit Date**:
   * pick a date, time and On-site / Remote, with a live check for weekend / holiday / leave / other visits that day;
   * the helpdesk gets a pop-up;
   * **Email Client to Schedule** sends the client a proposal with up to three dates. It is logged on the visit, and
     the client's replies thread to it.
   * Changing the date asks for a reason and is kept in the visit's **Reschedule History**. The helpdesk is copied.
     You can also drag the visit in the **PM Calendar**.
4. **Before the visit**: the engineer gets a preparation reminder, and the client gets a visit reminder (CC the engineer).
5. **Report.**
   * Each engineer attaches a **Visit Report** on their visit (→ *Report submitted*).
   * Or, for several engineers sharing one document: tick **Included in the combined AMC report** on each visit, and
     attach the **Combined PM Report** on the AMC.
   * When every visit is reported, the Account Manager is notified (*Reports submitted*).
6. **Sign off** (Account / Technical Manager). Attach the client sign-off if you have it, then click **Sign Off Cycle**:
   * a PM History row is added;
   * the next PM due date = previous due date + frequency;
   * a new cycle starts.

Moving the due date of a cycle that already has visits is blocked. Sign it off, or cancel its visits, first.

---

## 5. Notifications (Settings > Setup > Notification Rules)

There is one rule set per PM frequency: *Standard PM Notifications - Monthly / Quarterly / Half-yearly / Yearly*, and a
default for *All*. Day values differ by frequency; this table uses the Quarterly values.

| # | Rule | To | When |
|---|---|---|---|
| 1 | Helpdesk - assign engineers | role AMC Helpdesk | 30 days before due (Monthly 10, Half-yearly 45, Yearly 60), while *Not started* |
| 2 | Engineer - assigned, please schedule | the visit's engineer | when the helpdesk assigns them |
| 3 | Engineers - visit date still not set | engineers without a date (CC helpdesk) | 21 days before due, repeated every 3 days |
| 4 | Helpdesk - visit scheduled | role AMC Helpdesk (pop-up) | when an engineer sets a date |
| 5 | Engineer - visit preparation | the visit's engineer | 2 days before the visit (Monthly 1, Half-yearly/Yearly 3) |
| 6 | Client - visit reminder | the client contact + CC list (CC the engineer) | 2 days before the visit (Monthly 1) |
| 7 | Technical Manager - PM not scheduled | AMC technical manager (fallback: default / role) | 7 days before due (Monthly 3, Half-yearly 14, Yearly 30) if not scheduled |
| 8 | Overdue escalation | technical manager, CC account manager | from 1 day after due, **daily** until sign-off (ignores pause) |
| 9 | Visit rescheduled | the visit's engineer, CC helpdesk | every date change |
| 10 | Account Manager - reports ready for sign-off | AMC account manager | cycle becomes *Reports submitted* |
| 11 | Client - visit confirmation | client contact (CC engineer) | when a visit date is set. **Disabled** by default; enable it if you want it |

Each rule has these settings:

* **Recipient** (and CC):
  * *AMC Field* (account / technical manager, helpdesk contact);
  * *Visit Engineer*, *Cycle Engineers* or *Engineers Yet To Schedule*;
  * *Role*, *Specific User*, *Email Address* or *Client Contact*;
  * plus a *Fallback Role*.
* **Trigger**: days before / after the due date, days after a previous rule, a cycle status change, days before the
  visit date, or a visit being assigned / scheduled / rescheduled / reported.
* **Conditions**: *Only If Cycle Status In*, *Stop When Cycle Status*, *Repeat Every (days)*, *Ignore Pause*.
* **Channel**: Email, Teams, Email + Teams or System Notification, plus *Also Show Pop-up*.
* **Message**: Jinja *Subject / Message Template*, with Arabic versions (variables are listed in the field help).

How sending works:

* **No duplicates.** A rule is sent once per cycle, or once per visit for visit rules. It is recorded in the
  **Notification Log**, keyed by AMC, rule set, cycle, step, channel and visit.
* **Catch-up.** A missed day is caught up the next working day.
* **Retries.** A failed channel (e.g. Teams down) is retried on the next run.
* **Test Rules** (on a rule set) shows, for one AMC and a date, what would be sent to whom without sending anything.
  The AMC's **Notifications** tab shows the same as a timeline.

---

## 6. Office 365 Email Account

UI: **Search bar > Email Account > + Add Email Account**

| Field | Value |
|---|---|
| Email Address | `amc-notify@company.qa` (licensed mailbox or shared mailbox with SMTP AUTH allowed) |
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

Save. Frappe tests the SMTP login on save. Then click **AMC Settings > Test > Send Test Email**.

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

---

## 7. Settings (sidebar > Settings, Technical Manager)

* **Setup** tiles open Notification Rules, Notification Log, Engineer Leave, Public Holidays, Expertise and Users.

| Field | Meaning |
|---|---|
| Default Helpdesk Email | shared mailbox; used when a rule targets *helpdesk_contact* and the AMC has none |
| Default Technical Manager | used when an AMC has no technical manager; always receives the digest |
| Daily Overdue Digest / Recipients | one email (and Teams card) with every overdue AMC each morning |
| Renewal Alert Days (60) | the account manager is alerted this many days before *Contract End* |
| Teams / Default Teams Webhook URL | a Teams **Workflows** webhook ("Post to a channel when a webhook request is received") |
| Pop-up Notifications | on-screen pop-up + bell for users |
| Weekend Days (Friday,Saturday) / Skip Weekends and Holidays | nothing is sent on non-working days; reminders move to the nearest working day |
| Block Unavailable Visit Dates | off = warning, on = refuse a visit date on leave / holiday / double visit |
| Client Scheduling Email | optional Jinja override of the email sent to the client |
| Send Daily PM To-Do / Planning Horizon (45) / Client Reply Wait (3) | the helpdesk's daily to-do |
| Summary Frequency (Weekly) / Recipients | management summary: Sunday (last 7 days) or the 1st (last month) |
| Notification Language | English, Arabic, or English + Arabic in one email |

**Test** buttons: *Send Test Email*, *Send Test Teams Card*, *Send Test Pop-up To Me*, *Send PM To-Do Now*,
*Send Management Summary Now*, *Run Daily Job Now*.

---

## 8. Dashboards and reports

* **Dashboard** (helpdesk / managers):
  * cards: PM Due This Month, Overdue, Engineers To Assign, Visits To Schedule, Visits This Week, Reports Pending,
    Awaiting Sign-off and Follow-ups Due Today;
  * charts (managers): PM completed per month, on-time vs late, due per month, visits per engineer, and average
    days vs due date.
* **My Work** (engineers): My Visits To Schedule, My Visits Next 7 Days, My Reports Pending, plus quick links.
* **PM Calendar**:
  * visits coloured by status;
  * "PM due" markers for AMCs that still need engineers or dates;
  * public holidays shaded, and an engineer's leave shaded when you filter by engineer;
  * drag a visit to move it.
* **PM To-Do** (also emailed each working morning): follow-ups due, assign engineers, waiting for the engineer's date,
  awaiting client reply, visits in the next 2 working days, visits done with the report pending, ready for sign-off,
  and overdue.
* **Upcoming PM**: AMCs due in the next N days with their engineers and visit dates.
* **AMC Management Summary**: per client/AMC (signed-off cycles) or per engineer (reported visits) — completed,
  on-time %, average days vs due date, pending, overdue.
* **AMC Audit Trail**: who assigned engineers, changed visit dates, attached reports, signed off, changed due dates or
  status.

---

## 9. Excel import

* **Client** list > **Import > Download Excel Template**, fill the *Clients* sheet, then **Import > Import from Excel**.
* **AMC** list: same. The *AMCs* sheet has the AMC columns plus *Engineer (Engineers)* / *Expertise (Engineers)*.
  For an AMC with several engineers, add one row per extra engineer and leave the AMC columns empty on those rows.
* Import is for Technical Managers and System Managers (Data Import permission is granted on install).

---

## 10. Arabic

* **Screens:** users set *My Settings > Language = Arabic* and get a right-to-left desk with all AMC Tracker labels
  translated (`amc_tracker/translations/ar.csv`).
* **Notifications:** *Settings > Notification Language* = Arabic or English + Arabic. Every default rule has an
  Arabic subject and message you can edit.

---

## 11. Daily job

Cron `0 8 * * *` → `amc_tracker.notifications.scheduler.run_daily` (Asia/Qatar). It runs, in order:

1. every active AMC's rules (and its visits' rules);
2. the overdue digest;
3. renewal alerts;
4. the PM to-do;
5. the management summary (only on its day).

On a weekend day or public holiday, only the summary is checked.

```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.notifications.scheduler.run_daily
docker compose exec backend bench --site amc.localhost execute amc_tracker.notifications.scheduler.run_daily \
  --kwargs '{"on_date": "2026-11-01"}'        # simulate a date
docker compose exec backend bench --site amc.localhost scheduler status
```

---

## 12. Update, production image, backup

```bash
git pull && docker compose build && docker compose up -d
docker compose exec backend bench --site amc.localhost migrate
```
* If you edit a DocType / workspace / sidebar **JSON** by hand, bump its `"modified"` timestamp.
* Bump `__version__` in `amc_tracker/__init__.py` for releases.

### Production path: official "layered" image + `apps.json`
Put `apps/amc_tracker` in its own Git repository (the folder `apps/amc_tracker` becomes the repo root), then:
```bash
git clone https://github.com/frappe/frappe_docker && cd frappe_docker
cat > apps.json <<'JSON'
[ { "url": "https://github.com/YOUR-ORG/amc_tracker", "branch": "main" } ]
JSON
# private repo: "url": "https://<token>@github.com/YOUR-ORG/amc_tracker"  (passed as a BuildKit secret, never stored in layers)
docker build --no-cache \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-16 \
  --secret=id=apps_json,src=apps.json \
  --tag=amc-tracker:2.0.0 \
  --file=images/layered/Containerfile .
```
Then set `CUSTOM_IMAGE=amc-tracker` and `CUSTOM_TAG=2.0.0` in this repo's `.env`, and run `docker compose up -d` +
`bench migrate`. You can drop the `build:` section, or build in CI and push to your registry. The layered image builds
assets with `bench build` and contains only the apps listed (plus frappe). Pin `BASE_TAG` (e.g. `v16.50.0`) for
reproducible builds of the simple Dockerfile.

For HTTPS in production, put a reverse proxy (Traefik/Caddy/nginx) in front of port 8080. Set `SITE_NAME` to the FQDN
and `HOST_NAME=https://<FQDN>`. The websocket container must be able to reach `https://<FQDN>` (normal DNS).

---

```bash
./scripts/backup.sh                      # DB + files + site config -> ./backups
./scripts/restore.sh 20261009_183250     # restore a backup set by its timestamp prefix
```
Keep `.env` and the `*-site_config_backup.json` safe. The site encryption key is in it, and you need it to restore
encrypted passwords (e.g. the Email Account).

---

## 13. Project tree

```
amc-tracker/
├── .env.example · .dockerignore · .gitignore · apps.json.example
├── Dockerfile                       # FROM frappe/erpnext:v16 + apps/amc_tracker
├── docker-compose.yml               # backend, configurator, create-site, db, frontend, queues, redis, scheduler, websocket
├── docker-compose.apparmor.yml      # optional override for hosts with AppArmor (see TROUBLESHOOTING)
├── docs/ TEST_PLAN.md · TROUBLESHOOTING.md
├── scripts/ install.sh · backup.sh · restore.sh
└── apps/amc_tracker/amc_tracker/
    ├── hooks.py · permissions.py · utils.py · cycle.py (PM cycle: assign, status, sign-off) · scheduling.py
    ├── api/            calendar · scheduling_email · import_tools · metrics · number_cards · queries · tools
    ├── notifications/  engine · channels · templates (EN + AR) · scheduler · pm_todo · summary
    ├── setup/          install · default_flows · demo
    ├── public/js/      amc_tracker_popup.js · amc_tracker_ui.js (shared dialogs)
    ├── translations/   ar.csv
    └── amc_tracker/    module "AMC Tracker"
        ├── doctype/    client · amc · amc_engineer · expertise · pm_visit · pm_visit_expertise · pm_cycle ·
        │               pm_reschedule · client_contact_log · engineer_leave · public_holiday ·
        │               amc_notification_flow · amc_notification_step · amc_notification_log · amc_settings
        ├── report/     upcoming_pm · pm_to_do · amc_management_summary · amc_audit_trail
        ├── workspace/  amc_tracker (Dashboard) · my_work (engineers)
        ├── sidebar/    amc_tracker (role-based)
        └── number_card/ · dashboard_chart/ · dashboard_chart_source/
```
