// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("HC Engineer Leave", {
	setup(frm) {
		frm.set_query("engineer", () => ({
			query: "hc_tracker.api.queries.users_with_role",
			filters: { role: "HC Engineer" },
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.engineer && frappe.user.has_role("HC Engineer")) {
			frm.set_value("engineer", frappe.session.user);
		}
	},
});
