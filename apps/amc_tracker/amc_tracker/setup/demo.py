"""Sample users, clients and AMCs for the test plan (docs/TEST_PLAN.md).

    bench --site <site> execute amc_tracker.setup.demo.create_test_users --kwargs '{"password": "<choose one>"}'
    bench --site <site> execute amc_tracker.setup.demo.create_test_data
    bench --site <site> execute amc_tracker.setup.demo.delete_test_data

Everything created here uses the *.amc.test email domain and client codes T-xxx, so it is easy to spot and
remove. Do not run on production.
"""

import frappe
from frappe.utils import add_days, add_months, getdate, today

TEST_DOMAIN = "amc.test"

TEST_USERS = [
	# (email, full name, roles)
	(f"helpdesk@{TEST_DOMAIN}", "Hana Helpdesk", ["AMC Helpdesk"]),
	(f"eng1@{TEST_DOMAIN}", "Omar Engineer", ["AMC Engineer"]),  # Routing & Switching
	(f"eng2@{TEST_DOMAIN}", "Sara Engineer", ["AMC Engineer"]),  # Security / Firewall
	(f"eng3@{TEST_DOMAIN}", "Yousef Engineer", ["AMC Engineer"]),  # Wireless
	(f"eng4@{TEST_DOMAIN}", "Mariam Engineer", ["AMC Engineer"]),  # Data Center + Collaboration
	(f"am@{TEST_DOMAIN}", "Ali AccountManager", ["AMC Account Manager"]),
	(f"tm@{TEST_DOMAIN}", "Tariq TechManager", ["AMC Technical Manager"]),
]

RS, WL, SEC, DC, COLLAB = "Routing & Switching", "Wireless", "Security / Firewall", "Data Center", "Collaboration"


def _u(name):
	return f"{name}@{TEST_DOMAIN}"


def create_test_users(password: str):
	"""Create one user per role (four engineers). `password` is required (no default password)."""
	from frappe.utils.password import update_password

	if not password:
		frappe.throw("Pass a password: --kwargs '{\"password\": \"...\"}'")
	created = []
	for email, full_name, roles in TEST_USERS:
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			first, _sep, last = full_name.partition(" ")
			user = frappe.new_doc("User")
			user.update(
				{
					"email": email, "first_name": first, "last_name": last, "send_welcome_email": 0,
					"user_type": "System User", "time_zone": "Asia/Qatar",
				}
			)
			user.insert(ignore_permissions=True)
			created.append(email)
		user.add_roles(*roles)
		update_password(email, password)
	frappe.db.commit()
	return {"created": created, "users": [u[0] for u in TEST_USERS]}


CLIENTS = [
	# code, name, contact
	("T-001", "Al Noor Trading", "Ahmed Saleh"),
	("T-002", "Doha Logistics", "Fatima Al-Kuwari"),
	("T-003", "Pearl Hospitality", "John Matthews"),
	("T-004", "Lusail Engineering", "Khalid Hassan"),
	("T-005", "West Bay Clinics", "Dr. Noor Ali"),
	("T-006", "Msheireb Offices", "Priya Nair"),
]


def create_test_data(base_date=None):
	"""Clients T-001..T-006 and one AMC each, relative to `base_date` (default today):

	T-001 Monthly, due in 7 days, no engineers assigned yet          -> helpdesk "assign engineers" (rule 1)
	T-002 Quarterly, due in 20 days, engineer assigned, no date yet  -> waiting for the engineer
	T-003 Half-yearly, overdue by 3 days, one visit done without report, one not scheduled -> overdue escalation
	T-004 Yearly, due in 90 days, contract ends in 45 days           -> renewal alert
	T-005 Quarterly, due in 20 days, visit scheduled in 2 working days -> engineer prep + client reminder
	T-006 Half-yearly, due in 60 days, one engineer covering two areas (Data Center + Collaboration)
	"""
	from amc_tracker.cycle import assign_engineers
	from amc_tracker.scheduling import next_working_days

	base = getdate(base_date) if base_date else getdate(today())
	delete_test_data(keep_users=True)
	for i, (code, name, contact) in enumerate(CLIENTS, start=1):
		frappe.get_doc(
			{
				"doctype": "Client",
				"client_code": code,
				"client_name": name,
				"account_manager": _u("am"),
				"contact_name": contact,
				"contact_designation": "IT Manager",
				"contact_email": f"it{i}@client{i}.{TEST_DOMAIN}",
				"contact_phone": f"+974 5500 00{i:02d}",
				"preferred_contact_method": "Phone" if i % 2 else "Email",
			}
		).insert(ignore_permissions=True)

	def amc(code, title, frequency, due, engineers, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "AMC",
				"client": code,
				"amc_title": title,
				"frequency": frequency,
				"next_due_date": due,
				"technical_manager": _u("tm"),
				"contract_start": add_months(base, -6),
				"contract_end": add_months(base, 18),
				"engineers": [{"engineer": _u(e), "expertise": x} for e, x in engineers],
				**kw,
			}
		)
		return doc.insert(ignore_permissions=True)

	frappe.flags.in_import = True  # no notifications while building the demo
	try:
		a1 = amc("T-001", "Network AMC", "Monthly", add_days(base, 7), [("eng1", RS), ("eng3", WL)], scope="12 Catalyst 9300 switches, 1 C9800-L WLC")
		a2 = amc("T-002", "Security AMC", "Quarterly", add_days(base, 20), [("eng2", SEC)], scope="2 PA-3220 firewalls (HA)")
		a3 = amc("T-003", "Network & Security AMC", "Half-yearly", add_days(base, -3), [("eng1", RS), ("eng2", SEC)], scope="FortiGate 200F cluster, 8 Catalyst switches")
		a4 = amc(
			"T-004", "Data Center AMC", "Yearly", add_days(base, 90), [("eng4", DC)],
			contract_end=add_days(base, 45), scope="Nexus 9000 core, UCS chassis",
		)
		a5 = amc("T-005", "Wireless AMC", "Quarterly", add_days(base, 20), [("eng3", WL)], scope="AireOS 5520 WLC, 30 APs")
		a6 = amc("T-006", "DC & Collaboration AMC", "Half-yearly", add_days(base, 60), [("eng4", DC), ("eng4", COLLAB)], scope="Nexus 9300, CUCM cluster")

		assign_engineers(a2.name, [{"engineer": _u("eng2"), "expertise": [SEC]}])
		assign_engineers(a3.name, [{"engineer": _u("eng1"), "expertise": [RS]}, {"engineer": _u("eng2"), "expertise": [SEC], "visit_mode": "Remote"}])
		assign_engineers(a5.name, [{"engineer": _u("eng3"), "expertise": [WL]}])

		v3 = frappe.get_doc("PM Visit", {"amc": a3.name, "engineer": _u("eng1")})
		v3.visit_date = add_days(base, -6)
		v3.save(ignore_permissions=True)
		v5 = frappe.get_doc("PM Visit", {"amc": a5.name})
		v5.visit_date = next_working_days(base, 2)[-1]
		v5.save(ignore_permissions=True)
	finally:
		frappe.flags.in_import = False
	for name in (a1.name, a2.name, a3.name, a4.name, a5.name, a6.name):
		frappe.get_doc("AMC", name).save(ignore_permissions=True)  # refresh cycle status quietly
	frappe.db.commit()
	return [a1.name, a2.name, a3.name, a4.name, a5.name, a6.name]


def demo_amcs() -> list[str]:
	return frappe.get_all("AMC", filters={"client": ["like", "T-%"]}, pluck="name")


def delete_test_data(keep_users: bool = False):
	for name in demo_amcs():
		for visit in frappe.get_all("PM Visit", filters={"amc": name}, pluck="name"):
			frappe.db.delete("Communication", {"reference_doctype": "PM Visit", "reference_name": visit})
			frappe.delete_doc("PM Visit", visit, force=True, ignore_permissions=True)
		frappe.db.delete("AMC Notification Log", {"amc": name})
		frappe.db.delete("Client Contact Log", {"amc": name})
		frappe.db.delete("Communication", {"reference_doctype": "AMC", "reference_name": name})
		frappe.delete_doc("AMC", name, force=True, ignore_permissions=True)
	for code in frappe.get_all("Client", filters={"name": ["like", "T-%"]}, pluck="name"):
		frappe.delete_doc("Client", code, force=True, ignore_permissions=True)
	if not keep_users:
		for email, _name, _roles in TEST_USERS:
			frappe.db.delete("Engineer Leave", {"engineer": email})
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()
	return "deleted"


def configure_test_settings(teams_webhook_url: str | None = None, working_days: int = 0):
	"""AMC Settings used by the test plan (Technical Manager fallback, digest, pop-ups).

	working_days=0 turns off "Skip Weekends and Holidays" so the expected results of the test plan do not
	depend on the weekday it is run on; the working-days section turns it back on.
	"""
	settings = frappe.get_single("AMC Settings")
	settings.skip_non_working_days = 1 if int(working_days) else 0
	settings.default_technical_manager = _u("tm")
	settings.digest_recipients = f"noc@{TEST_DOMAIN}"
	settings.enable_daily_digest = 1
	settings.enable_popup_notifications = 1
	settings.renewal_alert_days = 60
	if teams_webhook_url:
		settings.enable_teams = 1
		settings.default_teams_webhook_url = teams_webhook_url
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return "AMC Settings configured for the test plan"
