"""v1.3 upgrade: helpdesk features.

* New HC Settings defaults (working days, to-do, management summary, language)
* Default flows get step 8 "Assigned Engineer - HC rescheduled", step 9 "Client - visit reminder",
  Arabic templates and 'Ignore Pause' on the overdue escalation
* Existing HC Cycle rows get Signed Off On / Due Date / Days Late where they can be derived
* Fixed-date Qatar public holidays, Data Import permission for Technical Managers
"""

import frappe
from frappe.utils import add_months, date_diff, getdate

from hc_tracker.setup.default_flows import FLOW_DEFINITIONS, upgrade_flow_to_v13
from hc_tracker.setup.install import grant_data_import_permission, seed_qatar_holidays, set_v13_defaults
from hc_tracker.utils import get_interval_months


def execute():
	settings = frappe.get_single("HC Settings")
	set_v13_defaults(settings)
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)

	for flow_name, _frequency, _default, days_from in FLOW_DEFINITIONS:
		if frappe.db.exists("HC Notification Flow", flow_name):
			upgrade_flow_to_v13(flow_name, days_from)

	# Backfill cycle metrics: due date of a closed cycle = next cycle's due date minus one interval
	for contract in frappe.get_all("HC Contract", fields=["name", "frequency", "next_due_date"]):
		rows = frappe.get_all(
			"HC Cycle",
			filters={"parent": contract.name, "parenttype": "HC Contract"},
			fields=["name", "hc_date", "due_date", "signed_off_on"],
			order_by="idx desc",
		)
		due = getdate(contract.next_due_date) if contract.next_due_date else None
		months = get_interval_months(contract.frequency)
		for row in rows:  # newest first
			due = add_months(due, -months) if due and months else None
			values = {}
			if not row.signed_off_on and row.hc_date:
				values["signed_off_on"] = row.hc_date
			if not row.due_date and due:
				values["due_date"] = due
				if row.hc_date:
					values["days_late"] = date_diff(row.hc_date, due)
			if values:
				frappe.db.set_value("HC Cycle", row.name, values, update_modified=False)

	seed_qatar_holidays()
	grant_data_import_permission()
