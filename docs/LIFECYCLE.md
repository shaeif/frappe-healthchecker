# AMC Tracker – Lifecycle guide

This guide follows one AMC from the first install to the next PM cycle:

1. set up the admin;
2. create the employees and engineer profiles;
3. create the client and AMC;
4. see what happens as the PM due date approaches;
5. assign the engineers, set visit dates, submit reports and sign off;
6. test the whole flow.

Every step names **who** does it and **where** in the UI. The example dates come from a real run of the built-in
walkthrough (section 9). Its base date was 10-10-2026 and the PM was due 15-11-2026.

Commands use the local site `amc.localhost`. Replace it with your `SITE_NAME`.

---

## 0. Roles at a glance

| Role | Who | Main jobs |
|---|---|---|
| **AMC Admin** | IT / application owner | Everything: users, engineer profiles, clients, AMCs, settings. **Only the AMC Admin (and System Manager) can change the notification rules.** |
| AMC Technical Manager | head of the technical team | Clients, AMCs, engineer profiles, sign-off, reports. Reads the settings but cannot change the notification rules. |
| AMC Account Manager | sales / account owner | Clients, AMCs, sign-off, management summary |
| AMC Helpdesk | helpdesk / coordinators | **Assigns engineers**, follows up the client, cancels / reopens visits, pauses reminders |
| AMC Engineer | field / remote engineers | Sees only their AMCs, **sets their own visit date**, attaches their report |

The **AMC Engineer** role is not given by hand. It is granted automatically when an **Engineer profile** is created
for the user (section 2).

---

## 1. Install and create the admin (once)

```bash
./scripts/install.sh --admin-email it.admin@company.qa --admin-name "IT Admin"
```

* The script creates the user `it.admin@company.qa` with the **AMC Admin** role and a random password.
* It prints the password at the end. Change it after the first login (avatar > *My Settings* > *Change Password*).
* Nothing is hard-coded: the database and Administrator passwords are generated into `.env`.

To make an existing user an admin later:
```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.install.create_admin_user \
  --kwargs '{"email": "it.admin@company.qa", "full_name": "IT Admin"}'
```
Without a password, the user gets the normal Frappe welcome email to set one.

Then the admin, logged in, does the following:

1. Set up the **Office 365 email account** (README section 6).
2. Open **sidebar > Settings** and set:
   * Default Helpdesk Email;
   * Default Technical Manager;
   * Teams webhook (optional);
   * Notification Language;
   * Weekend Days and *Skip Weekends and Holidays*.
3. Check **Settings > Setup > Public Holidays**. The Qatar holidays are loaded on install; add your company's own.
4. Optionally check **Settings > Setup > Notification Rules**. The four standard rule sets (Monthly / Quarterly /
   Half-yearly / Yearly) work out of the box. Only the admin sees this tile.

---

## 2. Create the employees (Admin)

### 2.1 Users

Each person needs a Frappe user. In the UI, go to **Settings > Setup > Users > + Add User**:

* email, first and last name;
* tick the role for non-engineers: *AMC Helpdesk*, *AMC Account Manager* or *AMC Technical Manager*.

From the command line:
```bash
docker compose exec backend bench --site amc.localhost add-user hana@company.qa --first-name Hana --last-name Helpdesk \
  --user-type "System User" --add-role "AMC Helpdesk" --password 'Choose-A-Strong-One'
docker compose exec backend bench --site amc.localhost add-user omar@company.qa --first-name Omar --last-name Engineer \
  --user-type "System User" --password 'Choose-A-Strong-One'
```

### 2.2 Areas of expertise

Go to **Settings > Setup > Expertise**. These are installed already:

* Routing & Switching
* Security / Firewall
* Data Center
* Collaboration
* Wireless

Add any others you need (e.g. *Server & Storage*, *SD-WAN*). Untick *Enabled* to retire one without losing history.

### 2.3 Engineer profiles

Go to **sidebar > Operations > Engineers > + Add Engineer** (the Admin, Technical Manager or Helpdesk can do this):

| Field | Example |
|---|---|
| User | `omar@company.qa`. **Any user can be an engineer**, including a helpdesk or manager user who also does visits. |
| Status | Active. Set it to *Inactive* when someone leaves or stops doing PM. Inactive engineers keep their history but cannot be assigned to new visits. |
| Mobile | +974 3300 0010 |
| Areas of Expertise | **one or several**, e.g. *Routing & Switching* + *Wireless* |

When you save:

* the user gets the **AMC Engineer** role automatically;
* their sidebar shows **My Work**.

The profile has buttons for *PM Visits*, *Leave*, *Calendar* and *Add Leave*.

**Engineer leave** is recorded from the engineer profile (*Add Leave*), or by the engineer from *My Work > My Leave*.
Leave and holidays are not on the sidebar. Both are used when a visit date is checked.

---

## 3. Create the client and the AMC (Account / Technical Manager or Admin)

### 3.1 Client

Go to **sidebar > Operations > Clients > + Add Client**:

* client code and name;
* account manager;
* primary contact: name, designation, email and phone;
* preferred contact method;
* **CC emails**, e.g. the client's NOC mailbox.

### 3.2 AMC

On the client, go to **+ AMC**, or **Operations > AMCs > + Add AMC**:

| Field | Example | Notes |
|---|---|---|
| AMC Title | Network & Security AMC | a client can have several AMCs |
| PM Frequency | Quarterly | chooses the rule set *Standard PM Notifications - Quarterly* |
| Next PM Due Date | 15-11-2026 | the date the current PM cycle must be completed by |
| Contract Start / End | 10-10-2026 / 09-10-2028 | renewal alert 60 days before the end |
| Account / Technical Manager | am@ / tm@ | recipients of sign-off and escalation |
| Scope | 2 firewalls, 12 switches | free text |
| **Engineers** table | engineer + expertise (+ lead) | the AMC's usual team |

In the **Engineers** table:

* Only **Active** engineers can be picked.
* When you pick an engineer, the row is filled with their expertise. If they have several areas, one row per area is
  added, and you delete the ones that are not in this AMC's scope.
* The expertise list in a row only offers the engineer's own areas.

Example: Lina (Routing & Switching + Wireless) gives two rows, and Karim (Security / Firewall) one row.

Bulk loading: **Client / AMC list > Import > Download Excel Template** (README section 9).

The AMC's **cycle label** (e.g. *2026-Q4*) and **cycle status** (*Not started*) are calculated automatically.

---

## 4. The due date approaches – what is sent, to whom, and when

From the moment the AMC exists, the daily job (08:00 Asia/Qatar) evaluates its rules every working day.

The table below shows the Quarterly rule set for a PM due **15-11-2026**. Other frequencies use different day values
(README section 5).

| When | Rule | To | Condition |
|---|---|---|---|
| due − 30 days | 1. Helpdesk – assign engineers | AMC Helpdesk (email + pop-up) | cycle still *Not started* |
| when assigned | 2. Engineer – assigned, please schedule your visit | each assigned engineer | one per visit |
| due − 21 days, every 3 days | 3. Engineers – visit date still not set | engineers **without a date** (CC helpdesk) | cycle *Engineers assigned* |
| when a date is set | 4. Helpdesk – visit scheduled | helpdesk (pop-up) | one per visit |
| on every date change | 9. Visit rescheduled | that engineer, CC helpdesk | reason is required |
| visit − 2 days | 5. Engineer – visit preparation | the visit's engineer | one per visit |
| visit − 2 days | 6. Client – visit reminder | client contact + CC emails, CC engineer | one per visit |
| due − 7 days | 7. Technical Manager – PM not scheduled | technical manager | only if not every visit has a date |
| all reports in | 10. Account Manager – reports ready for sign-off | account manager | cycle *Reports submitted* |
| due + 1 day, daily | 8. Overdue escalation | technical manager, CC account manager | until sign-off, ignores pause |

How sending behaves:

* **Working days.** With *Skip Weekends and Holidays* on, nothing is sent on Friday, Saturday or a public holiday.
  A reminder planned for such a day goes out on the next working day, so nothing is lost.
* **No duplicates.** Each rule is sent once per cycle, or once per visit for visit rules. Running the job twice the
  same day sends nothing new. This is recorded in the **Notification Log** (Settings > Setup).
* **Pausing.** A helpdesk user can pause reminders, e.g. when the client asks to wait. Use *Log Client Contact >
  Pause Reminders Until* on the AMC. The overdue escalation ignores the pause.
* **See it in advance.** The AMC's **Notifications** tab shows the timeline: every rule, its planned date, recipients
  and state (Pending / Sent / Skipped and why).

Timeline of the example AMC, as shown on 10-10-2026 before anything happened:

```
    16-10-2026  1. Helpdesk - assign engineers  -> helpdesk@amc.test  (Pending: Planned for 16-10-2026)
    25-10-2026  3. Engineers - visit date still not set  -> -  (Skipped: Cycle status is Not started; rule only applies while it is Engineers assigned)
    08-11-2026  7. Technical Manager - PM not scheduled  -> tm@amc.test  (Pending: Planned for 08-11-2026)
    16-11-2026  8. Overdue escalation  -> tm@amc.test  (Pending: Planned for 16-11-2026)
      on event  10. Account Manager - reports ready for sign-off  -> am@amc.test  (Pending: Waiting for the status change)
      on event  11. Client - visit confirmation  -> -  (Skipped: Rule disabled)
      on event  2. Engineer - assigned, please schedule your visit  -> -  (Pending: Waiting for a visit event)
      on event  4. Helpdesk - visit scheduled  -> -  (Pending: Waiting for a visit event)
      on event  5. Engineer - visit preparation  -> -  (Pending: No PM visits with a date in this cycle yet)
      on event  6. Client - visit reminder  -> -  (Pending: No PM visits with a date in this cycle yet)
      on event  9. Visit rescheduled  -> -  (Pending: Waiting for a visit event)
```

Rule 3 shows *Skipped* only because no engineer is assigned yet. It becomes *Pending* after the assignment.

---

## 5. Helpdesk assigns the engineers

The helpdesk gets rule 1 (email + pop-up) and sees the AMC under **PM To-Do > Assign engineers** and on the
dashboard card *Engineers To Assign*.

On the AMC, open the **PM Cycle** tab > **Assign Engineers**:

* The dialog lists the AMC's engineers, one row per engineer and area. Add, remove or change rows, and choose
  **On-site** or **Remote** per engineer.
* The cases you have are all supported:
  * **One engineer collects everything:** use only that engineer, with one row per area (Routing & Switching,
    Security / Firewall, …). The rows are merged into one visit.
  * **Every engineer visits on a different date:** keep one row per engineer.
  * **Some on-site, some remote:** set the mode per row.
* **One PM Visit per engineer** is created for this cycle. An engineer with two areas gets one visit covering both.
* Assigning someone who is not yet in the AMC's Engineers table adds them to it.
* Only engineers with an **Active** profile can be assigned.

Result: the cycle status becomes **Engineers assigned**, and each engineer receives rule 2.

From the example run:
```
  2 PM visits created; cycle status Engineers assigned
      -> rule 2 'Engineer - assigned, please schedule your visit' by Email to lc.engineer@amc.test [Sent]
      -> rule 2 'Engineer - assigned, please schedule your visit' by Email to lc.engineer2@amc.test [Sent]
  25-10-2026 daily job - 21 days before due: engineers without a date are reminded
      -> rule 3 'Engineers - visit date still not set' by Email to lc.engineer@amc.test, lc.engineer2@amc.test cc helpdesk@amc.test [Sent]
```

---

## 6. Engineers choose the visit date

The engineer opens **My Work > My Visits To Schedule** (or the link in the email). On the PM Visit, they click
**Set Visit Date** and enter:

* the date, from / to time, and On-site or Remote;
* the dialog checks the date live for weekend, public holiday, the engineer's leave, and other visits that week;
* *Block Unavailable Visit Dates* in Settings makes the check a hard stop instead of a warning.

Optionally, **Email Client to Schedule** sends the client up to three proposed dates. The email is logged on the
visit, and the client's replies thread to it.

What happens next:

* The helpdesk gets rule 4 (pop-up).
* When **every** visit has a date, the cycle status becomes **Scheduled**.
* **Rescheduling** (Set Visit Date again, or dragging the visit in the **PM Calendar**) asks for a reason. The change
  is kept in the visit's *Reschedule History*, and rule 9 goes to the engineer, CC the helpdesk.

From the example run:
```
  Lina sets 03-11-2026 (on-site)
  Karim sets 04-11-2026 (remote); cycle status Scheduled
      -> rule 4 'Helpdesk - visit scheduled' by pop-up to helpdesk@amc.test [Sent]   (x2, one per visit)
  Karim moves his visit to 05-11-2026 (client request)
      -> rule 9 'Visit rescheduled' by Email to lc.engineer2@amc.test cc helpdesk@amc.test [Sent]
```

If no date is set by **due − 7 days**, the technical manager gets rule 7.

---

## 7. Before the visit

Two days before each visit:

* the engineer gets the **preparation** reminder (rule 5);
* the client gets the **visit reminder** (rule 6), CC the engineer.

```
  01-11-2026 daily job - 2 days before Lina's visit: preparation + client reminder
      -> rule 5 'Engineer - visit preparation' by Email to lc.engineer@amc.test [Sent]
      -> rule 6 'Client - visit reminder' by Email to it@lifecycle.amc.test, noc@lifecycle.amc.test cc lc.engineer@amc.test [Sent]
  03-11-2026 daily job - 2 days before Karim's visit
      -> rule 5 ... to lc.engineer2@amc.test, rule 6 ... cc lc.engineer2@amc.test
```

---

## 8. Reports, sign-off and the next cycle

### 8.1 Reports – separate or combined

There are two ways to submit reports:

* **Separate:** each engineer attaches a **Visit Report** on their own visit. The visit becomes *Report submitted*.
* **Combined:** for several engineers sharing one document, each of them ticks **Included in the combined AMC
  report** on their visit. One of them (or the helpdesk / a manager) attaches the **Combined PM Report** on the AMC.
* The two ways can be mixed in the same cycle. In the example, Lina attached her own report and Karim's visit is in
  the combined report.

*Mark Completed* records that a visit is done while its report is still pending. Such visits appear in the PM To-Do
under *Reports pending*.

When every visit is reported, the cycle status becomes **Reports submitted**, and the account manager gets rule 10:
```
  Lina attaches her report; Karim's visit is in the combined report -> cycle Reports submitted
      -> rule 10 'Account Manager - reports ready for sign-off' by Email to am@amc.test [Sent]
```

### 8.2 Sign-off

The Account Manager, Technical Manager or Admin does the sign-off. On the AMC, attach the client sign-off if you have
it, then click **Sign Off Cycle**:

* the cycle is archived in **PM History**, with its due date, completion date, visits and reports;
* **the next PM due date = previous due date + frequency**: 15-11-2026 + 3 months = **15-02-2027**;
* the new cycle *2027-Q1* starts as **Not started**, and the whole timeline starts again from section 4.

```
  Cycle 2026-Q4 signed off. Next PM due on 15-02-2027. New cycle 2027-Q1, status Not started; PM History rows: 1
```

### 8.3 If it runs late

From **due + 1 day**, the technical manager (CC the account manager) gets the **overdue escalation** every working
day until sign-off. The AMC also appears in the **daily overdue digest** and under *Overdue* in the PM To-Do.

### 8.4 Contract end

60 days before *Contract End* (see Settings > *Renewal Alert Days*), the account manager gets a **renewal alert**.
To close an AMC, set its status to *Expired* or *Cancelled*. Its reminders stop.

---

## 9. Testing the lifecycle

Use a **test site** for everything in this section. The demo data uses the `@amc.test` domain and client codes `T-xxx`
and `LC-001`.

### 9.1 Preview one AMC's timeline (safe on production, sends nothing)

* In the UI, open the AMC > **Notifications** tab.
* An admin can also use **Notification Rules > (rule set) > Test Rules**, then pick an AMC and a date.
* From the command line:
```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.lifecycle.preview_timeline \
  --kwargs '{"amc": "AMC-2026-0001"}'
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.lifecycle.preview_timeline \
  --kwargs '{"amc": "AMC-2026-0001", "on_date": "2026-11-10"}'      # as it will look on that date
```

### 9.2 Run the whole lifecycle automatically (test site)

```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.lifecycle.run_walkthrough
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.lifecycle.run_walkthrough \
  --kwargs '{"base_date": "2026-10-10"}'        # reproduce the dates used in this guide
```

The walkthrough does the following:

1. Creates two engineers with profiles:
   * Lina (`lc.engineer@amc.test`): Routing & Switching + Wireless;
   * Karim (`lc.engineer2@amc.test`): Security / Firewall.
2. Creates the client **LC-001 Lifecycle Trading** and a quarterly AMC due in 35 days, and prints its timeline.
3. Runs the daily job on simulated dates:
   * 35 days before the due date, when nothing is due yet;
   * 30 days before (rule 1), then the same day again to show that nothing is sent twice;
   * 21 days before (rule 3).
4. Assigns both engineers (rule 2), sets visit dates (rule 4) and reschedules one visit (rule 9).
5. Runs the job 2 days before each visit (rules 5 and 6).
6. Submits reports, one separate and one combined (rule 10).
7. Signs off and shows the rolled-forward due date.

Every notification is printed with its channel, recipients and status. The output shown in sections 4–8 comes from
this command.

In the example, 30 days before the due date (16-10-2026) is a Friday, so the run used the next working day,
Sunday 18-10-2026. This also shows the catch-up.

The data is kept so you can open the AMC in the browser and look at the visits, PM History, Notification Log and
timeline. To remove it:
```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.setup.lifecycle.delete_walkthrough
```

Email needs an outgoing email account (README section 6):

* **Without one**, every email step is logged as **Failed** with "No default outgoing Email Account". It is retried
  on the next run. The pop-ups are still **Sent**.
* **With one**, the emails are *Sent* to the Email Queue. The `@amc.test` addresses never reach anyone.

### 9.3 Simulate any date for all AMCs

```bash
docker compose exec backend bench --site amc.localhost execute amc_tracker.notifications.scheduler.run_daily \
  --kwargs '{"on_date": "2026-10-18"}'
```

This runs every active AMC's rules, the overdue digest, renewal alerts and the PM To-Do as if it were that day. Check
the results in **Settings > Setup > Notification Log** (filter by *Run Date*).

### 9.4 Click through it in the browser, one role at a time

Install with demo users:
```bash
./scripts/install.sh --demo --admin-email it.admin@company.qa
```
The demo users all share the password printed by the script.

| # | Log in as | Do | Expect |
|---|---|---|---|
| 1 | `admin@amc.test` (AMC Admin) | Sidebar > Settings | Settings with *Notification Rules* and the Test buttons |
| 2 | admin | Operations > Engineers > + Add: a new user, two areas of expertise | Saved; the user now has the *AMC Engineer* role |
| 3 | admin | Operations > Clients > + Add, then + AMC (Quarterly, due in 35 days), Engineers table: pick the new engineer | Rows filled with the engineer's areas |
| 4 | admin | AMC > Notifications tab | Timeline like section 4 |
| 5 | `tm@amc.test` (Technical Manager) | Sidebar > Settings | Read-only, **no** Notification Rules tile; opening `/desk/amc-notification-flow` is refused |
| 6 | `helpdesk@amc.test` | The AMC > PM Cycle > **Assign Engineers** | One PM Visit per engineer; cycle *Engineers assigned* |
| 7 | the engineer | My Work > My Visits To Schedule > Set Visit Date | Availability check; cycle *Scheduled* once all have dates; helpdesk pop-up |
| 8 | the engineer | Set Visit Date again (new date + reason) | Reschedule History row; email to the engineer CC helpdesk |
| 9 | the engineer | Attach the Visit Report (or tick *Included in the combined report* + combined report on the AMC) | Visit *Report submitted*; cycle *Reports submitted* |
| 10 | `am@amc.test` | AMC > **Sign Off Cycle** | PM History row; due date + 3 months; cycle *Not started* |
| 11 | admin | Operations > Engineers > the engineer > Status = Inactive | Can no longer be assigned ("has no active Engineer profile") |

The full test plan, with the sample clients T-001..T-006 and expected results per notification rule, is in
[`TEST_PLAN.md`](TEST_PLAN.md).

### 9.5 Automated tests

```bash
docker compose exec backend bench --site amc.localhost set-config allow_tests true
docker compose exec backend bench --site amc.localhost run-tests --app amc_tracker
```
