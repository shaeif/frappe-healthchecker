// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("HC Notification Log", {
	refresh(frm) {
		if (frm.doc.contract) {
			frm.add_custom_button(__("Open Contract"), () =>
				frappe.set_route("Form", "HC Contract", frm.doc.contract)
			);
		}
	},
});
