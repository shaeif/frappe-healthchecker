// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("HC Settings", {
	refresh(frm) {
		frm.add_custom_button(
			__("Send Test Email"),
			() =>
				frappe.prompt(
					{
						fieldname: "recipient",
						fieldtype: "Data",
						options: "Email",
						label: __("Recipient"),
						reqd: 1,
						default: frappe.session.user_email,
					},
					(values) =>
						frappe.call({
							method: "hc_tracker.api.tools.send_test_email",
							args: values,
							freeze: true,
							callback: (r) => r.message && frappe.msgprint(r.message),
						}),
					__("Send Test Email")
				),
			__("Test")
		);

		frm.add_custom_button(
			__("Send Test Teams Card"),
			() =>
				frappe.call({
					method: "hc_tracker.api.tools.send_test_teams_message",
					args: { webhook_url: frm.doc.default_teams_webhook_url },
					freeze: true,
					callback: (r) => r.message && frappe.msgprint(r.message),
				}),
			__("Test")
		);

		frm.add_custom_button(
			__("Send Test Pop-up To Me"),
			() =>
				frappe.call({
					method: "hc_tracker.api.tools.send_test_popup",
					callback: (r) => r.message && frappe.show_alert(r.message),
				}),
			__("Test")
		);

		frm.add_custom_button(
			__("Run Daily Job Now"),
			() =>
				frappe.call({
					method: "hc_tracker.notifications.scheduler.enqueue_daily_run",
					callback: (r) => r.message && frappe.msgprint(r.message),
				}),
			__("Test")
		);
	},
});
