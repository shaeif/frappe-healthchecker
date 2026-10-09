# HC Tracker – Test Plan

All commands assume the stack is running (`docker compose up -d`) and `S` is your site name:

```bash
S=hc.localhost
alias b='docker compose exec backend bench --site '"$S"
# macOS: replace $(date -d '+1 day' +%F) below with $(date -v+1d +%F)
```

Every result below was produced on Frappe 16.50.0 with this repository. `D` = the day you run the test
(the "base date"). Sample users use the non-deliverable domain `hc.test`. Emails to them stay in the
**Email Queue**, which is enough to verify the flow. To receive real mail, change the users' emails or add yourself
to *HC Settings > Digest Recipients*.

---

## 0. Preparation

```bash
# 0.1 Sample users (one per role). Pass your own password.
b execute hc_tracker.setup.demo.create_test_users --kwargs '{"password": "Test#HC-2026!"}'

# 0.2 HC Settings for the test (Technical Manager fallback, digest, pop-ups)
b execute hc_tracker.setup.demo.configure_test_settings
#     optional Teams: --kwargs '{"teams_webhook_url": "<your Workflows URL>"}'

# 0.3 Office 365 Email Account configured (README section 6) -> HC Settings > Test > Send Test Email

# 0.4 Sample contracts T-001..T-008 (all four frequencies), dates relative to today
b execute hc_tracker.setup.demo.create_test_contracts
```

Check: **HC Contract** list shows 8 contracts with indicators: T-003 **red "Overdue 3d"**; T-006 / T-001 / T-002
**orange "Due in Nd"**; others green. Each contract's *Notification Flow* field shows the flow for its
frequency (e.g. T-001 → `Standard HC Escalation - Monthly`), and *Interval (months)* is 1 / 3 / 6 / 12.

| ID | Frequency | Next due | Special |
|---|---|---|---|
| T-001 | Monthly | D+7 | – |
| T-002 | Quarterly | D+7 | – |
| T-003 | Half-yearly | D−3 (overdue) | – |
| T-004 | Yearly | D+90 | contract_end D+45 |
| T-005 | Quarterly | D+20 | created as *Scheduled*, scheduled_date D+3 |
| T-006 | Monthly | D+3 | **no Technical Manager** on the contract |
| T-007 | Half-yearly | D+60 | used for status-change tests |
| T-008 | Yearly | D+30 | – |

Note: T-005 is created with status *Scheduled*, so **step 2 (Engineer – HC booked)** is sent as soon as it is
saved. That is the *On status change* behaviour.

---

## 1. Daily run – each step of the default flow

```bash
b execute hc_tracker.notifications.scheduler.run_daily
```
Expected output similar to `{"date": "...", "flow_logs": 27, "digest": "Email: Sent", "renewal_alerts": 2}`.

Open **HC Notification Log** (group by Contract or filter `Status = Sent`). Expected *Sent* steps:

| Contract | Steps sent | Why |
|---|---|---|
| T-001 Monthly | **1 Helpdesk** | 7 days before due (Monthly first reminder = 7) |
| T-002 Quarterly | **1 Helpdesk, 4 Technical Manager** | step 1 planned D−23 (caught up, `<=` check), step 4 at 7 days before due, status still *Not started* |
| T-003 Half-yearly | **1, 4, 5 Overdue** | step 5 = 1 day after due; TM **+ CC Account Manager**; Email + Teams |
| T-004 Yearly | only **Contract renewal alert** (step 0) | due in 90 days (step 1 planned at 60 days) – renewal because contract ends in 45 ≤ 60 days |
| T-005 Quarterly | **2 (at creation), 3 Engineer prep reminder** | 3 days before scheduled date; CC Helpdesk |
| T-006 Monthly | **1, 4** | step 4 recipient = `tm@hc.test` from *HC Settings > Default Technical Manager* (contract field empty) |
| T-007 Half-yearly | none | step 1 planned at 45 days before due |
| T-008 Yearly | **1, 4** | 60 and 30 days before due |
| (none) | **Daily overdue digest** | T-003 is overdue |

Each step writes **one log row per channel**: `Email`, `Teams` (only when Teams is enabled),
and `System Notification` (pop-up + bell, when *Also Show Pop-up* is on and the recipient is a system user).

Helpdesk → Engineer → Technical Manager chain (subjects in the log / Email Queue):
* Helpdesk: `[HC] Book health check: Al Noor Trading due …` ("Contact the client and book the HC window").
* Engineer: `[HC] In 3 days: West Bay Clinics on …` (prep reminder) and `[HC] Booked for …` (booking).
* Technical Manager: `[HC] Escalation - not booked, due in 7 days: Doha Logistics` (Email + Teams).

**Email Queue** (search bar > Email Queue): one email per *Email* log row, with recipients and CC as above.

If the Office 365 Email Account is not configured yet, every *Email* row is **Failed** with
"No default outgoing Email Account…" while the pop-up rows are *Sent*. Configure the account and run the job
again: only the failed email channels are retried (including the status-change step 2 of T-005), and the pop-ups
are not repeated.

---

## 2. No duplicates on a second run

```bash
b execute hc_tracker.notifications.scheduler.run_daily
```
Expected: the number of *Sent* rows in HC Notification Log does not change; the digest is not re-sent.

---

## 3. "Only if status" skipping

* **T-005** (status *Scheduled*): step 1 Helpdesk and step 4 Technical Manager are **not** sent. Open T-005 >
  **Notifications** tab: both show **Skipped – "Status is Scheduled; step only fires while status is Not started"**.
* Book T-002 (see section 6) and run the daily job on a later date: step 4 is not sent again, and step 1 shows
  *Sent* (it was already sent before the booking).

---

## 4. Repeat while overdue + skipped runs

```bash
b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "'$(date -d '+1 day' +%F)'"}'
b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "'$(date -d '+4 day' +%F)'"}'
```
Filter HC Notification Log: `Contract = T-003`, `Step No = 5`, `Channel = Email`. Expect **3 rows**
(run dates D, D+1, D+4). Skipping D+2 and D+3 produces **one** catch-up send on D+4, not three. The T-003 timeline shows
"Next repeat on …". The overdue escalation stops once T-003 is signed off (status `Signed off` is in *Stop When Status*
and the cycle rolls over).

---

## 5. "Days after previous step if not resolved"

1. Open **HC Notification Flow > Standard HC Escalation - Monthly**. In the steps table, edit **step 7
   "Helpdesk follow-up (not booked)"**: tick **Enabled** (Trigger = *Days after previous step if not resolved*,
   Trigger Days = 3, After Step No = 1, Only If Status In = *Not started*). Save.
2. Run on D+2 and D+3 (T-001's step 1 was sent on D):
   ```bash
   b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "'$(date -d '+2 day' +%F)'"}'
   b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "'$(date -d '+3 day' +%F)'"}'
   ```
   Expected: no step 7 log after D+2; **step 7 sent for T-001 on D+3** (subject `[HC] Reminder - still not booked: …`).
   If T-001 were booked first (status *Scheduled*), step 7 would be **Skipped**.
   (If you already ran section 4's D+4 run with step 7 enabled, it has fired there. That is also correct.)

---

## 6. Status change: Helpdesk books, Engineer is notified (+ pop-up)

1. Open two browsers (or a private window): log in as **helpdesk@hc.test** in one and **eng1@hc.test** in the other,
   using the password from step 0.1, at `http://<SITE_NAME>:8080`.
2. As **helpdesk@hc.test**, open **T-007** and try to change *Client Name*, then save. You get the error
   **"Helpdesk can only change Status and Scheduled Date"**. Reload.
3. Click **Mark Scheduled**, pick a date (e.g. D+10), and confirm.
   * **eng1@hc.test** (assigned engineer) immediately gets an **on-screen pop-up**
     "[HC] Booked for …: Msheireb Offices" with an **Open Contract** button, and the bell shows a new notification.
   * The helpdesk user also gets the pop-up (CC: role HC Helpdesk).
   * HC Notification Log: T-007 step 2, Email + System Notification, *Sent*.
4. As helpdesk, try to set T-007 to *Report sent*. Error: **"Helpdesk can only change the status from Not
   started to Scheduled."**

Pop-up smoke test for any user: **HC Settings > Test > Send Test Pop-up To Me**.

---

## 7. Engineer visibility and report upload → Report sent

1. As **eng1@hc.test**, open the **HC Contract** list. It shows only T-001, T-002, T-005, T-007 (contracts where eng1
   is the Assigned Engineer). Opening `/desk/hc-contract/T-003` gives *Not permitted*.
2. Open **T-007**, set status *In progress*, and save. Go to the **Current Cycle** tab, attach a PDF in
   **Current Report**, fill *Findings Summary*, and save.
   * Status becomes **Report sent** automatically (green alert "Report attached: status set to Report sent").
   * **am@hc.test** receives step 6 `[HC] Report ready - get client sign-off: Msheireb Offices`
     (email + pop-up): "Send report to client and get sign-off."
3. As eng1, set status *Signed off* and save. Blocked: **"Only an HC Account Manager or HC Technical Manager can
   set the status to Signed off."**

---

## 8. Blocked sign-off without report

As **am@hc.test**, open **T-001** (no report attached), set status **Signed off**, and save.
Expected: **"Attach the HC report (Current Report) before signing off."** The status stays unchanged.

---

## 9. Sign-off rolls the due date and restarts the flow

As **am@hc.test**, open **T-007** (status *Report sent*, report attached) and click **Sign Off Cycle** (or set status
*Signed off*). Optionally attach the client-signed file in *Current Sign-off* first. Then save.

Expected (example where the previous due date was 2026-12-08, Half-yearly):
* Alert "Cycle 2026-H2 signed off. Next due date: 2027-06-08 …"
* **Status = Not started**, **Next Due Date = previous due + 6 months** (from the previous **due date**, not
  from today); *Last HC Date* = the scheduled date.
* **History** tab: a new **HC Cycle** row with HC Date, Period `2026-H2`, Engineer, Report, Sign-off File,
  Findings, Signed Off By.
* *Current Report*, *Current Sign-off*, *Findings Summary* and *Scheduled Date* are cleared.
* **Notifications** tab: the cycle is now `2027-H1` and every step is *Pending* again (fresh cycle). List indicator:
  grey **Signed off** for 14 days.

Repeat for a **Monthly** (T-001: +1 month), **Quarterly** (T-002: +3) and **Yearly** (T-008: +12) contract.

---

## 10. Test Flow dry run

As **Administrator** or **tm@hc.test**, open **HC Notification Flow > Standard HC Escalation - Half-yearly** and click
**Test Flow**. Pick contract **T-003**, *Evaluate As Of* = a date 10 days ahead, and click **Run Dry Run**.
Expected: a table of all steps. Step 5 shows **"Would send today"** (repeat due) with To `tm@hc.test`, CC
`am@hc.test` and the rendered subject `[HC] OVERDUE by 13 days: …`. The other steps show Sent / Pending / Skipped with
the reason. The text "Dry run: nothing is sent and nothing is logged" appears, and the HC Notification Log count is
unchanged.

---

## 11. Notification log and timeline

* **HC Notification Log** list: green *Sent* / red *Failed* indicators, filters on Contract, Cycle, Channel and Status.
  A failed channel stores the error, e.g. "No default outgoing Email Account…" or "Teams webhook returned HTTP 400…".
  It is retried on the next run.
* Contract > **Notifications** tab: **Notification Timeline** shows each step with planned date, recipients, channels
  and status. Use *Notifications > Refresh Timeline* and *Notifications > Notification Log*.
* Workspace **HC Tracker**: number cards *Due This Month*, *Overdue*, *Awaiting Sign-off*,
  *Notifications Failed Today*.
* Report **Upcoming Health Checks**: filter by Engineer (e.g. eng1@hc.test) and Status; next 90 days (+ overdue).

---

## 12. Overdue digest

After section 1: HC Notification Log has a row **"Daily overdue digest"** (Cycle `digest-<date>`, Channel Email, plus
Teams if enabled). The email (Email Queue → open → *Preview*) contains an HTML table with
**Client | Due date | Days overdue | Engineer | Status | Last step sent**, listing T-003 ("Pearl Hospitality", 3 days,
"Sara Engineer", "Not started", "5. Overdue escalation (date)"). Recipients: `noc@hc.test` + the Technical Managers.
It is sent once per day: a second run the same day does not resend it.

---

## 13. Renewal alert

After section 1: **T-004** has a log row **"Contract renewal alert"** (Cycle `renewal-<contract_end>`) to
`am@hc.test` (Email + pop-up). The subject is `[HC] Contract renewal: Lusail Engineering ends in 45 days (…)`.
It is sent only once per contract end date. Changing *Contract End* on the contract starts a new alert window.

---

## 14. Teams (optional)

Set a real Workflows webhook in HC Settings and tick *Enable Teams*. Click **Test > Send Test Teams Card**: an
Adaptive Card appears in the channel. Then run the daily job on a fresh test set (`create_test_contracts` again):
step 4 and step 5 post cards with Client / Due date / Status / Engineer / Step facts and an **Open in HC Tracker**
button. The digest posts an orange "Attention" card listing the overdue contracts.

---

## 15. Clean up

```bash
b execute hc_tracker.setup.demo.delete_test_data
```

## Automated tests (optional, test site only)

`run-tests` creates Frappe's own test records (users, email accounts…). Run it on a throw-away site, never on
production.

```bash
b set-config allow_tests true
b run-tests --app hc_tracker          # 6 tests: default flows, interval/period labels, report -> Report sent,
                                      # blocked sign-off, due-date roll-over, idempotent daily run
```
