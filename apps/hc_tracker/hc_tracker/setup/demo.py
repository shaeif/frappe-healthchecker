"""Sample users and contracts for the test plan (docs/TEST_PLAN.md).

    bench --site <site> execute hc_tracker.setup.demo.create_test_users --kwargs '{"password": "<choose one>"}'
    bench --site <site> execute hc_tracker.setup.demo.create_test_contracts
    bench --site <site> execute hc_tracker.setup.demo.delete_test_data

Everything created here uses the *.hc.test email domain and client IDs T-xxx, so it is easy to
spot and remove. Do not run on production.
"""

import frappe
from frappe.utils import add_days, add_months, getdate, today

TEST_DOMAIN = "hc.test"

TEST_USERS = [
	# (email, first name, roles)
	(f"helpdesk@{TEST_DOMAIN}", "Hana Helpdesk", ["HC Helpdesk"]),
	(f"eng1@{TEST_DOMAIN}", "Omar Engineer", ["HC Engineer"]),
	(f"eng2@{TEST_DOMAIN}", "Sara Engineer", ["HC Engineer"]),
	(f"am@{TEST_DOMAIN}", "Ali AccountManager", ["HC Account Manager"]),
	(f"tm@{TEST_DOMAIN}", "Tariq TechManager", ["HC Technical Manager"]),
]


def create_test_users(password: str):
	"""Create one user per HC role. `password` is required (no default password)."""
	if not password:
		frappe.throw("Pass a password: --kwargs '{\"password\": \"...\"}'")
	created = []
	for email, first_name, roles in TEST_USERS:
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.new_doc("User")
			user.update(
				{
					"email": email,
					"first_name": first_name,
					"send_welcome_email": 0,
					"user_type": "System User",
					"time_zone": "Asia/Qatar",
				}
			)
			user.insert(ignore_permissions=True)
			created.append(email)
		user.add_roles(*roles)
		from frappe.utils.password import update_password

		update_password(email, password)
	frappe.db.commit()
	return {"created": created, "users": [u[0] for u in TEST_USERS]}


def create_test_contracts(base_date=None):
	"""Create T-001..T-008 relative to `base_date` (default today), covering all four frequencies."""
	base = getdate(base_date) if base_date else getdate(today())
	tm = f"tm@{TEST_DOMAIN}"
	am = f"am@{TEST_DOMAIN}"
	eng1 = f"eng1@{TEST_DOMAIN}"
	eng2 = f"eng2@{TEST_DOMAIN}"

	contracts = [
		# Monthly, due in 7 days -> step 1 (Helpdesk, 7 days before) fires today
		dict(client_id="T-001", client_name="Al Noor Trading", frequency="Monthly", next_due_date=add_days(base, 7),
			assigned_engineer=eng1, account_manager=am, technical_manager=tm,
			scope="12 Catalyst 9300 switches, 1 C9800-L WLC"),
		# Quarterly, due in 7 days, nobody booked -> step 1 (30 days) + step 4 Technical Manager (7 days)
		dict(client_id="T-002", client_name="Doha Logistics", frequency="Quarterly", next_due_date=add_days(base, 7),
			assigned_engineer=eng1, account_manager=am, technical_manager=tm,
			scope="2 PA-3220 firewalls (HA), 20 Catalyst 9200 switches"),
		# Half-yearly, overdue by 3 days -> steps 1, 4 and 5 (overdue, repeats daily)
		dict(client_id="T-003", client_name="Pearl Hospitality", frequency="Half-yearly", next_due_date=add_days(base, -3),
			assigned_engineer=eng2, account_manager=am, technical_manager=tm,
			scope="FortiGate 200F cluster, 8 Catalyst switches"),
		# Yearly, due in 90 days -> nothing yet (step 1 is 60 days before); contract ends in 45 days -> renewal alert
		dict(client_id="T-004", client_name="Lusail Engineering", frequency="Yearly", next_due_date=add_days(base, 90),
			assigned_engineer=eng2, account_manager=am, technical_manager=tm,
			contract_start=add_months(base, -11), contract_end=add_days(base, 45),
			scope="Nexus 9000 core, 2 PA-5220"),
		# Quarterly, already booked in 3 days -> step 3 (engineer prep reminder); step 1 skipped (status Scheduled)
		dict(client_id="T-005", client_name="West Bay Clinics", frequency="Quarterly", next_due_date=add_days(base, 20),
			status="Scheduled", scheduled_date=add_days(base, 3),
			assigned_engineer=eng1, account_manager=am, technical_manager=tm,
			scope="AireOS 5520 WLC, 30 APs, 6 switches"),
		# Monthly, due in 3 days but no Technical Manager on the contract -> step 4 uses
		# HC Settings default / role HC Technical Manager (fallback)
		dict(client_id="T-006", client_name="Corniche Retail", frequency="Monthly", next_due_date=add_days(base, 3),
			assigned_engineer=eng2, account_manager=am,
			scope="FortiGate 100F, 4 switches"),
		# Half-yearly, due in 60 days -> nothing yet (step 1 at 45 days); used for the status-change tests
		dict(client_id="T-007", client_name="Msheireb Offices", frequency="Half-yearly", next_due_date=add_days(base, 60),
			assigned_engineer=eng1, account_manager=am, technical_manager=tm,
			scope="Catalyst 9500 core, C9800-40 WLC"),
		# Yearly, due in 30 days -> step 1 (60) and step 4 (30) both due today
		dict(client_id="T-008", client_name="Qatar Marine Services", frequency="Yearly", next_due_date=add_days(base, 30),
			assigned_engineer=eng2, account_manager=am, technical_manager=tm,
			scope="2 PA-850, 10 switches"),
	]

	names = []
	for values in contracts:
		if frappe.db.exists("HC Contract", values["client_id"]):
			frappe.delete_doc("HC Contract", values["client_id"], force=True, ignore_permissions=True)
		doc = frappe.new_doc("HC Contract")
		doc.update(values)
		doc.insert(ignore_permissions=True)
		names.append(doc.name)
	frappe.db.commit()
	return names


def delete_test_data():
	for name in frappe.get_all("HC Contract", filters={"name": ["like", "T-%"]}, pluck="name"):
		frappe.db.delete("HC Notification Log", {"contract": name})
		frappe.delete_doc("HC Contract", name, force=True, ignore_permissions=True)
	for email, _first, _roles in TEST_USERS:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()
	return "deleted"
