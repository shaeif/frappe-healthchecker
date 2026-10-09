// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("Client", {
	setup(frm) {
		frm.set_query("account_manager", () => ({
			query: "amc_tracker.api.queries.users_with_role",
			filters: { role: "AMC Account Manager" },
		}));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frappe.model.can_create("AMC")) {
			frm.add_custom_button(__("New AMC"), () =>
				frappe.new_doc("AMC", { client: frm.doc.name, account_manager: frm.doc.account_manager })
			);
		}
		frm.add_custom_button(__("AMCs"), () => frappe.set_route("List", "AMC", { client: frm.doc.name }), __("View"));
		frm.add_custom_button(__("PM Visits"), () => frappe.set_route("List", "PM Visit", { client: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Contact Log"), () => frappe.set_route("List", "Client Contact Log", { client: frm.doc.name }), __("View"));
	},
});
