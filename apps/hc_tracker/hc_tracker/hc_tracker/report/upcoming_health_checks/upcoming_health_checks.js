// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["Upcoming Health Checks"] = {
	filters: [
		{
			fieldname: "days",
			label: __("Next N Days"),
			fieldtype: "Int",
			default: 90,
		},
		{
			fieldname: "engineer",
			label: __("Engineer"),
			fieldtype: "Link",
			options: "User",
			get_query: () => ({
				query: "hc_tracker.api.queries.users_with_role",
				filters: { role: "HC Engineer" },
			}),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nNot started\nScheduled\nIn progress\nReport sent",
		},
		{
			fieldname: "include_overdue",
			label: __("Include Overdue"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_left" && data) {
			const color = data.days_left < 0 ? "red" : data.days_left <= 14 ? "orange" : "green";
			value = `<span style="color: var(--${color}-600, ${color}); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
