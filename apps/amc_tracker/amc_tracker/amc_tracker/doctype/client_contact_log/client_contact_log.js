// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("Client Contact Log", {
	setup(frm) {
		frm.set_query("pm_visit", () => ({ filters: { amc: frm.doc.amc || "" } }));
	},
});
