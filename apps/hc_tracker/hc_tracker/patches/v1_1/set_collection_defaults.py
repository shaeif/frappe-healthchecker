import frappe

from hc_tracker.setup.install import set_collection_defaults


def execute():
	"""Phase 2 upgrade: give the new HC Settings collection fields their defaults on existing sites."""
	settings = frappe.get_single("HC Settings")
	set_collection_defaults(settings)
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)
