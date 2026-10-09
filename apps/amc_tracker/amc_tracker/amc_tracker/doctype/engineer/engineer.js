// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("Engineer", {
	setup(frm) {
		frm.set_query("user", () => ({ filters: { user_type: "System User", enabled: 1 } }));
		frm.set_query("expertise", () => ({ filters: { enabled: 1 } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("PM Visits"), () => frappe.set_route("List", "PM Visit", { engineer: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Leave"), () => frappe.set_route("List", "Engineer Leave", { engineer: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Calendar"), () => frappe.set_route("List", "PM Visit", "Calendar", "default"), __("View"));
		if (frappe.model.can_create("Engineer Leave")) {
			frm.add_custom_button(__("Add Leave"), () => frappe.new_doc("Engineer Leave", { engineer: frm.doc.name }));
		}
	},
});
