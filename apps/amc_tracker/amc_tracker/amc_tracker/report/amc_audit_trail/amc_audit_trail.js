// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["AMC Audit Trail"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "amc", label: __("AMC"), fieldtype: "Link", options: "AMC" },
		{ fieldname: "user", label: __("User"), fieldtype: "Link", options: "User" },
		{
			fieldname: "change",
			label: __("Change"),
			fieldtype: "Select",
			options: ["", "Engineer assigned", "Engineers", "Visit Date", "Visit Status", "Visit Report", "Sign-off", "Next PM Due Date", "Contract Status"],
		},
	],
};
