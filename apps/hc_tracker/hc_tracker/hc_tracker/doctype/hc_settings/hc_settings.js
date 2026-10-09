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
			__("Send Helpdesk To-Do Now"),
			() =>
				frappe.call({
					method: "hc_tracker.notifications.helpdesk_todo.send_todo_now",
					callback: (r) => r.message && frappe.msgprint(r.message),
				}),
			__("Test")
		);

		frm.add_custom_button(
			__("Send Management Summary Now"),
			() =>
				frappe.prompt(
					[
						{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
						{ fieldname: "to_date", fieldtype: "Date", label: __("To Date"), default: frappe.datetime.add_days(frappe.datetime.get_today(), -1), reqd: 1 },
					],
					(values) =>
						frappe.call({
							method: "hc_tracker.notifications.summary.send_summary_now",
							args: values,
							freeze: true,
							callback: (r) => r.message && frappe.msgprint(r.message),
						}),
					__("Send Management Summary")
				),
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
