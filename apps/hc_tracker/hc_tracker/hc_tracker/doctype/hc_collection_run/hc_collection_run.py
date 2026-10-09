# Copyright (c) 2026, HC Tracker Maintainers and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HCCollectionRun(Document):
	pass


@frappe.whitelist()
def use_as_current_report(run: str):
	"""Attach the run's draft PDF as the contract's Current Report (moves status to Report sent)."""
	run_doc = frappe.get_doc("HC Collection Run", run)
	run_doc.check_permission("read")
	if not run_doc.report_file:
		frappe.throw(_("This collection run has no report file."))
	contract = frappe.get_doc("HC Contract", run_doc.contract)
	contract.check_permission("write")
	contract.current_report = run_doc.report_file
	if not contract.findings_summary:
		contract.findings_summary = run_doc.findings_summary
	contract.save()
	return contract.status
