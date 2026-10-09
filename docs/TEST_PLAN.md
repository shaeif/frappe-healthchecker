# AMC Tracker – Test Plan

Every expected result below was produced with this repository on Frappe 16.

* `D` = the day you run the test.
* Sample users use the non-deliverable domain `amc.test`. Their emails stay in the **Email Queue**, which is enough
  to check who gets what. To receive real mail, add yourself to *Settings > Digest Recipients*.

```bash
S=amc.localhost
b() { docker compose exec backend bench --site "$S" "$@"; }
```

---

## 0. Preparation

```bash
./scripts/install.sh --demo        # or, on an existing site:
b execute amc_tracker.setup.demo.create_test_users --kwargs '{"password": "Choose-One-2026!"}'
b execute amc_tracker.setup.demo.configure_test_settings   # Skip Weekends OFF so results don't depend on the weekday
b execute amc_tracker.setup.demo.create_test_data
```

Users (one per role, four engineers):

| User | Role | Expertise in the demo |
|---|---|---|
| helpdesk@amc.test | AMC Helpdesk | – |
| eng1@amc.test (Omar) | AMC Engineer | Routing & Switching |
| eng2@amc.test (Sara) | AMC Engineer | Security / Firewall |
| eng3@amc.test (Yousef) | AMC Engineer | Wireless |
| eng4@amc.test (Mariam) | AMC Engineer | Data Center + Collaboration |
| am@amc.test | AMC Account Manager | – |
| tm@amc.test | AMC Technical Manager | – |

Clients and AMCs:

| Client | AMC | PM frequency | Due | State after creation |
|---|---|---|---|---|
| T-001 Al Noor Trading | Network AMC (eng1 R&S, eng3 Wireless) | Monthly | D+7 | Not started |
| T-002 Doha Logistics | Security AMC (eng2) | Quarterly | D+20 | Engineers assigned, no date |
| T-003 Pearl Hospitality | Network & Security AMC (eng1, eng2) | Half-yearly | D−3 (**overdue**) | eng1 visited D−6 without report; eng2 (remote) no date |
| T-004 Lusail Engineering | Data Center AMC (eng4) | Yearly | D+90 | Not started; **contract ends D+45** |
| T-005 West Bay Clinics | Wireless AMC (eng3) | Quarterly | D+20 | visit scheduled in 2 working days |
| T-006 Msheireb Offices | DC & Collaboration AMC (eng4 with two areas) | Half-yearly | D+60 | Not started |

Optional: create the Office 365 Email Account (README §6) and use *Settings > Test > Send Test Email*.

---

## 1. Role-based screens

Log in as each user and check the sidebar:

* **helpdesk@**:
  * sidebar: Dashboard; Operations (Clients, AMCs, PM Visits, PM Calendar, PM To-Do, Contact Log); Reports (Upcoming PM);
  * **no** Settings, Notification Rules / Log, Engineer Leave or Holidays;
  * the Dashboard shows 8 cards (PM Due This Month, Overdue = 1, Engineers To Assign…).
* **eng2@**:
  * sidebar: *My Work* (My Visits To Schedule = 2, My Visits Next 7 Days, My Reports Pending), Operations
    without PM To-Do, Upcoming PM;
  * **AMCs** lists only T-002 and T-003; **Clients** only T-002 and T-003.
* **tm@**: everything, plus Management Summary, Audit Trail and **Settings**. Settings > *Setup* shows tiles for
  Notification Rules, Notification Log, Engineer Leave, Public Holidays, Expertise and Users.

## 2. Daily run

```bash
b execute amc_tracker.notifications.scheduler.run_daily
```
Expected output similar to
`{"notification_logs": 13, "digest": "Email: Sent", "renewal_alerts": 2, "pm_todo": "Email: Sent, System Notification: Sent", ...}`.

**AMC Notification Log** (sidebar > Settings > Notification Log):

| AMC | Rule | Recipient |
|---|---|---|
| T-001 | 1 Helpdesk - assign engineers | helpdesk@ |
| T-003 | 3 Engineers - visit date still not set | **eng2@ only** (eng1 already has a date), CC helpdesk |
| T-003 | 7 Technical Manager - PM not scheduled | tm@ |
| T-003 | 8 Overdue escalation | tm@, CC am@ |
| T-005 | 5 Engineer - visit preparation (per visit) | eng3@ |
| T-005 | 6 Client - visit reminder | it5@client5.amc.test |
| T-004 | AMC renewal alert | am@ |
| – | Daily overdue digest, Daily PM to-do | noc@ + tm@ / helpdesk@ |

Run it again: nothing new is sent (rule 8 repeats only the next day).

## 3. Assign engineers (helpdesk)

1. As **helpdesk@**, open T-001's AMC > **PM Cycle** tab > **Assign Engineers**.
2. The dialog lists eng1 (Routing & Switching) and eng3 (Wireless). Set eng3 to **Remote**, then click **Assign**.
3. Expected:
   * two PM Visits (*To be scheduled*);
   * cycle status **Engineers assigned**;
   * rule 2 emails eng1 and eng3 separately ("please schedule your PM visit").
4. Try changing *PM Frequency* as helpdesk: refused ("You cannot change: PM Frequency").
5. Assign again: "Already assigned: …". Engineers keep one visit per cycle; use **Add Visit** for a second one.

## 4. Engineer sets the date

1. As **eng1@**, *My Work* > *My PM Visits* > T-001 > **Set Visit Date**.
2. Pick a working day.
   * The dialog shows "Engineer available and working day" and the other visits that week.
   * Pick a Friday instead: it warns "weekend (Friday)".
3. Save the date. Expected:
   * the visit is *Scheduled*;
   * the helpdesk gets a pop-up (rule 4).
4. Open eng3's visit as eng1: it is read-only ("This visit belongs to Yousef Engineer…"). Engineers edit only their own visits, and the server refuses it too.
5. **Reschedule** as eng1, reason *Client request*. Expected:
   * a row in *Reschedule History*;
   * rule 9 emails eng1 with CC to helpdesk, subject "[AMC] Visit moved to …".
6. As eng3 set a date too. Expected: the AMC cycle becomes **Scheduled**.
7. **PM Calendar** (sidebar). The visits appear in blue; "PM due" markers show AMCs still needing engineers or dates.
   Drag a visit to another day: its date changes, with reason *Changed in calendar*.

## 5. Leave, holidays, availability

* As **eng3@**, **My Leave** > New: *Training* on a working day `W`. Then set eng3's visit to `W`: a warning names
  the training.
* As tm@, tick *Settings > Block Unavailable Visit Dates* and try again: the save is refused. Untick it.
* **Settings > Public Holidays** lists National Sport Day and Qatar National Day (18 Dec). Add the Eid dates here.

## 6. Client communication

* On T-002's visit, as **eng2@**: **Client > Email Client to Schedule**. Add two proposed dates, then **Send**.
  Expected:
  * an email to it2@client2.amc.test, CC eng2 and the client's CC list;
  * the email shows on the visit's timeline;
  * a Contact Log entry *Scheduling email sent*;
  * the AMC's *Scheduling Email Sent On* is set.
* **Log Client Contact** on T-006: *No answer* (the follow-up date defaults to +2 days). On that date T-006 is under
  *Follow-ups due today* in the **PM To-Do**.
* *Client asked for later date* with *Pause Reminders Until* D+10. Expected:
  * the AMC banner shows "Reminders paused until …";
  * date-based rules wait, but the overdue escalation (*Ignore Pause*) still fires.

## 7. Reports and sign-off

1. As **eng1@**, attach a **Visit Report** on the T-001 visit: it becomes *Report submitted*, and the cycle *In progress*.
2. As **eng3@**:
   * tick **Included in the combined AMC report** on your visit, set *Completed On* and save (the visit is *Completed*);
   * on the AMC, attach the **Combined PM Report**.
   
   Expected: eng3's visit becomes *Report submitted*, the cycle **Reports submitted**, and rule 10 emails am@.
3. As helpdesk@: there is no *Sign Off Cycle* button (the API refuses with "Only an AMC Account Manager or AMC Technical
   Manager…").
4. As **am@**: click **Sign Off Cycle**. Expected:
   * "Cycle 2026-10 signed off. Next PM due on …" (previous due + 1 month);
   * a **History** row with the engineers, combined report and signer;
   * cycle status *Not started*.
5. Try sign-off on T-003 (eng2 has no report): "Reports are missing for: Sara Engineer (To be scheduled)".

## 8. PM To-Do, dashboards, reports

* **PM To-Do** (as helpdesk@ or am@):
  * T-001 or T-006 under *Assign engineers*;
  * T-002 and T-003 under *Waiting for the engineer to set the visit date*;
  * T-005 under *Visits in the next 2 working days*;
  * T-003 under *Visit done - report pending* and *Overdue*;
  * **Email To-Do Now** sends it.
* **Upcoming PM**: each AMC with its engineers and visit dates; the Days Left column is coloured.
* **AMC Management Summary** (am@): *Client / AMC* shows T-001 completed = 1. *Engineer* shows Omar / Yousef with
  completed visits, and Sara with pending + overdue.
* **AMC Audit Trail** (tm@): for T-001 there are *Engineer assigned*, *Visit Date*, *Visit Report*, *Combined PM Report*
  and *Sign-off* rows, with the user and time.
* **Dashboard** charts (tm@):
  * Completed per Month, On-time vs Late and Avg Days fill after the first sign-off;
  * Due per Month and Visits per Engineer fill immediately.

## 9. Notification rules

* **Settings > Notification Rules > Standard PM Notifications - Quarterly > Test Rules**: pick T-005 and D. The dry
  run lists every rule, the visit it applies to, recipients, channels and "Would send today", and sends nothing.
* The AMC **Notifications** tab shows the same timeline for that AMC.
* Add a rule with recipient *Visit Engineer* and trigger *Days before due date*. Saving is refused (it needs a visit
  trigger).
* Enable rule 11 *Client - visit confirmation*, then set a visit date. The client gets a confirmation email.

## 10. Excel import (tm@)

* **Client** list > **Import > Download Excel Template**. Add `T-101, Imported Client`, then **Import from Excel** >
  *Start Import*.
* **AMC** list > template:
  * row 1: `T-101 | Imported AMC | Quarterly | <date> | ... | eng1@amc.test | Routing & Switching`;
  * row 2: only `eng2@amc.test | Security / Firewall`.
  
  Import: one AMC with two engineers.

## 11. Arabic

* am@ > *My Settings > Language = Arabic*: the desk is right-to-left, and the sidebar, forms and reports are in Arabic.
* *Settings > Notification Language = English + Arabic*, then trigger a rule (e.g. reschedule a visit). The email
  has the English text, a line, then the Arabic text right-aligned. Set it back to English.

## 12. Working days

```bash
b execute amc_tracker.setup.demo.configure_test_settings --kwargs '{"working_days": 1}'
b execute amc_tracker.notifications.scheduler.run_daily --kwargs '{"on_date": "<next Friday>"}'
```
Expected: `{"skipped": "non-working day", ...}`. A reminder that falls on a Friday shows "(moved to working day)" in
Test Rules.

## 13. Clean up

```bash
b execute amc_tracker.setup.demo.delete_test_data
```

## Automated tests (test site only)

```bash
b set-config allow_tests true
b run-tests --app amc_tracker     # 7 tests: rule sets, assign -> one visit per engineer, cycle status + combined
                                  # report + sign-off roll-over, reschedule history, idempotent daily run, rule validation
```
