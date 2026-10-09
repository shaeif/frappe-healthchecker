// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["Helpdesk To-Do"] = {
	filters: [
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "section",
			label: __("Action"),
			fieldtype: "Select",
			options: [
				"",
				"Follow-ups due today",
				"Awaiting client reply",
				"Book now (not booked yet)",
				"Confirm with client (booked in the next 2 working days)",
				"Overdue",
			],
		},
	],
};
