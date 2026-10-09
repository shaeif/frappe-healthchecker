"""v1.2: device data collection was removed from HC Tracker (helpdesk scheduling/notification tool only).

Deletes everything the collection feature stored on existing sites:
* collection run files (draft PDF reports and raw device output ZIPs),
* collection runs, results and findings,
* the contract Devices table, including the encrypted device credentials,
* the collection settings in HC Settings.
Reports that were already attached to a contract as Current Report / history are kept.
"""

import os

import frappe

REMOVED_DOCTYPES = ["HC Collection Finding", "HC Collection Result", "HC Collection Run", "HC Device"]
REMOVED_SETTINGS = [
	"enable_device_collection",
	"auto_collect_on_scheduled_date",
	"fill_findings_summary",
	"collection_parallelism",
	"device_timeout",
	"cpu_threshold",
	"memory_threshold",
	"uptime_threshold_days",
	"license_warning_days",
]


def execute():
	# 1. Files attached to collection runs. Deleted directly: File.on_trash would try to load the removed
	#    HC Collection Run controller. A file still used elsewhere (e.g. "Use as Current Report") is kept.
	for f in frappe.get_all(
		"File", filters={"attached_to_doctype": "HC Collection Run"}, fields=["name", "file_url"]
	):
		url = f.file_url or ""
		shared = frappe.db.exists("File", {"file_url": url, "name": ["!=", f.name]})
		if url.startswith(("/files/", "/private/files/")) and not shared:
			folder = "private" if url.startswith("/private/") else "public"
			path = frappe.get_site_path(folder, "files", os.path.basename(url))
			if os.path.isfile(path):
				os.remove(path)
		frappe.db.delete("File", f.name)

	# 2. Encrypted device credentials
	frappe.db.delete("__Auth", {"doctype": "HC Device"})

	# 3. Data tables and DocType records
	for doctype in REMOVED_DOCTYPES:
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")
		for child in ("DocField", "DocPerm", "Custom DocPerm", "DocType Link", "DocType Action"):
			frappe.db.delete(child, {"parent": doctype})
		frappe.db.delete("DocType", {"name": doctype})
		frappe.db.delete("Version", {"ref_doctype": doctype})

	# 4. Collection settings
	frappe.db.delete("Singles", {"doctype": "HC Settings", "field": ["in", REMOVED_SETTINGS]})
	frappe.clear_cache()
