// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["HC Audit Trail"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "contract", label: __("Contract"), fieldtype: "Link", options: "HC Contract" },
		{ fieldname: "user", label: __("User"), fieldtype: "Link", options: "User" },
		{
			fieldname: "field",
			label: __("Change"),
			fieldtype: "Select",
			options: ["", "Status", "Scheduled Date", "Next Due Date", "Assigned Engineer", "Current Report", "Sign-off", "Reminders Paused Until"],
		},
	],
};
