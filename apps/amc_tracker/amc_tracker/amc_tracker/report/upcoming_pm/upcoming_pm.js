// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.query_reports["Upcoming PM"] = {
	filters: [
		{ fieldname: "days", label: __("Next N Days"), fieldtype: "Int", default: 90 },
		{ fieldname: "include_overdue", label: __("Include Overdue"), fieldtype: "Check", default: 1 },
		{ fieldname: "client", label: __("Client"), fieldtype: "Link", options: "Client" },
		{
			fieldname: "engineer",
			label: __("Engineer"),
			fieldtype: "Link",
			options: "User",
			get_query: () => ({ query: "amc_tracker.api.queries.users_with_role", filters: { role: "AMC Engineer" } }),
		},
		{
			fieldname: "cycle_status",
			label: __("Cycle Status"),
			fieldtype: "Select",
			options: ["", "Not started", "Engineers assigned", "Scheduled", "In progress", "Reports submitted"],
		},
		{ fieldname: "frequency", label: __("PM Frequency"), fieldtype: "Select", options: ["", "Monthly", "Quarterly", "Half-yearly", "Yearly"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_left" && data) {
			const color = data.days_left < 0 ? "red" : data.days_left <= 14 ? "orange" : "green";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
