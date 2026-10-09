// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("Engineer Leave", {
	setup(frm) {
		frm.set_query("engineer", () => ({
			query: "amc_tracker.api.queries.users_with_role",
			filters: { role: "AMC Engineer" },
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.engineer && frappe.user.has_role("AMC Engineer")) {
			frm.set_value("engineer", frappe.session.user);
		}
	},
});
