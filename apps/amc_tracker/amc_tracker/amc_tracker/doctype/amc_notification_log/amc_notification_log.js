// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("AMC Notification Log", {
	refresh(frm) {
		if (frm.doc.amc) frm.add_custom_button(__("Open AMC"), () => frappe.set_route("Form", "AMC", frm.doc.amc));
		if (frm.doc.pm_visit) frm.add_custom_button(__("Open PM Visit"), () => frappe.set_route("Form", "PM Visit", frm.doc.pm_visit));
	},
});
