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

# 0.2 HC Settings for the test (Technical Manager fallback, digest, pop-ups). It also turns
#     "Skip Weekends and Holidays" off so sections 1-14 give the same results on any weekday;
#     section 15 turns it back on.
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

## 15. v1.3 helpdesk features

Run 15.1 to 15.10 after section 14 (the sample contracts must still exist). Log in as **helpdesk@hc.test**
unless a step says otherwise. `N` = the next Friday after D, `W` = a working day (Sun-Thu) 5-8 days after D that
is not a holiday.

### 15.1 Weekend and holidays
```bash
b execute hc_tracker.setup.demo.configure_test_settings --kwargs '{"working_days": 1}'
b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "N"}'
```
Expected: `{"date": "N", "skipped": "non-working day", "management_summary": "..."}`. **HC Holiday** lists
National Sport Day and Qatar National Day (18 Dec) for this year and next. **Test Flow** on a contract whose
reminder would land on a Friday shows the planned date with "(moved to working day)".

### 15.2 Engineer leave and booking checks
1. **HC Engineer Leave > New**: Engineer `eng1@hc.test`, Leave Type *Training*, From/To = `W`. Save.
2. Open **T-001 > Helpdesk > Book Health Check**, pick `W`. The dialog shows a yellow **Check before booking**
   box: "Omar Engineer is on training from W to W", plus the engineer's bookings that week.
3. Pick `N` instead: the box says it is a weekend day.
4. As Administrator tick *HC Settings > Block Unavailable Bookings* and book T-001 on `W`: the save is refused with
   the same message. Untick it again.

### 15.3 Book and reschedule
1. T-001 > Book Health Check on a free working day `B` (no leave): status *Scheduled*; step 2 is sent to the engineer.
2. Change *Scheduled Date* to `B`+2 and save: a prompt asks for the **Reschedule Reason** (pick *Client request*,
   add a note). *Current Cycle > Reschedule History* has a row (old date, new date, reason, note, you).
   **HC Notification Log** has step 8 *Assigned Engineer - HC rescheduled* for T-001 (engineer, CC helpdesk),
   subject `[HC] Rescheduled to …`.

### 15.4 Booking Calendar
Contract list > **Booking Calendar**. Booked contracts appear on their scheduled date, unbooked ones as
"Due: <client>" on their due date. Drag a "Due" item (e.g. T-002) to a working day: it becomes *Scheduled* on that
day. Drag it again: the date changes and a reschedule row with reason *Changed in calendar* is added.

### 15.5 Booking request email
T-008 > **Helpdesk > Send Booking Request**, fill two proposed dates, **Send**. Check:
* **Email Queue**: one mail to T-008's *Client Contact Email* listing the two dates;
* the contract timeline shows the email (Communication);
* *Booking Request Sent On* is set and **HC Contact Log** has *Booking request sent*.

### 15.6 Contact log, follow-up, pause
T-004 > **Helpdesk > Log Contact Attempt**: Method *Phone*, Outcome *Client asked for later date*,
Pause Reminders Until = D+10. Save. The contract shows *Reminders Paused Until* D+10 and a banner; its
**Notification Timeline** shows date-based steps as "Reminders paused until …" (the overdue escalation, which has
*Ignore Pause*, is not held back). Log another attempt on T-006 with Outcome *No answer* and Follow Up On = D.
The workspace card **Follow-ups Due Today** shows 1.

### 15.7 Helpdesk to-do
Open the **Helpdesk To-Do** report (date D): T-006 under *Follow-ups due today*, T-003 under *Overdue*,
unbooked contracts due within 45 days under *Book now*. As Administrator click **HC Settings > Send Helpdesk To-Do
Now**: one email to the HC Helpdesk users in the Email Queue, and a pop-up for each of them. After 3 days
(Client Reply Wait), T-008 moves to *Awaiting client reply*:
```bash
b execute hc_tracker.notifications.helpdesk_todo.build_todo --kwargs '{"on_date": "D+3"}'
```

### 15.8 Client visit reminder (step 9)
For the contract booked in 15.3, run the daily job 2 days before the booked date (1 day for Monthly):
```bash
b execute hc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "<booked date - 1>"}'
```
If that day is a Friday, Saturday or holiday, use the working day before it. HC Notification Log: step 9
*Client - visit reminder* to T-001's *Client Contact Email*, CC the HC Helpdesk users.

### 15.9 Management summary, charts, audit trail
* As **tm@hc.test**: *HC Settings > Send Management Summary Now* → email with completed / on time / late /
  overdue per client. The **HC Management Summary** report shows the same with a chart (Group By Client or Engineer).
  Helpdesk users get "You don't have access" for this report.
* Workspace: four charts under **Performance**; T-007 (signed off in section 9) shows as one completed, on-time HC.
* **HC Audit Trail** (Technical Manager): filter Contract = T-001 → status, scheduled date and reschedule rows
  with the user and time.

### 15.10 Excel import and Arabic
* As **tm@hc.test**, contract list > **Import > Download Excel Template**: workbook with a *Contracts* sheet (one column per field) and a
  *Help* sheet. Add a row (Client ID `T-101`, name, frequency *Monthly*, next due date, engineer, account manager)
  and use **Import > Import from Excel** → *Start Import*. T-101 is created with interval 1 and the Monthly flow.
* Set *My Settings > Language* = **Arabic** for am@hc.test and log in: the desk is right-to-left and HC Tracker
  labels are Arabic.
* *HC Settings > Notification Language* = **English + Arabic**, then book a contract: the step 2 email has the
  English text, a line, and the Arabic text right-aligned. Set it back to English.

---

## 16. Clean up

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

Run the tests on a non-working day too: `test_daily_run_is_idempotent` passes either way (the daily job skips,
or sends once).
