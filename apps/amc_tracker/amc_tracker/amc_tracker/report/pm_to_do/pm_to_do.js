// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["PM To-Do"] = {
	filters: [
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "section",
			label: __("Action"),
			fieldtype: "Select",
			options: [
				{ value: "", label: "" },
				{ value: "follow_up", label: __("Follow-ups due today") },
				{ value: "assign", label: __("Assign engineers") },
				{ value: "not_scheduled", label: __("Waiting for the engineer to set the visit date") },
				{ value: "awaiting_reply", label: __("Awaiting client reply") },
				{ value: "upcoming", label: __("Visits in the next 2 working days (confirm with client)") },
				{ value: "reports", label: __("Visit done - report pending") },
				{ value: "signoff", label: __("Ready for sign-off") },
				{ value: "overdue", label: __("Overdue") },
			],
		},
	],
	onload(report) {
		if (frappe.user.has_role(["AMC Helpdesk", "AMC Technical Manager", "AMC Admin", "System Manager"])) {
			report.page.add_inner_button(__("Email To-Do Now"), () =>
				frappe.xcall("amc_tracker.notifications.pm_todo.send_todo_now").then((msg) => frappe.msgprint(msg))
			);
		}
	},
};
