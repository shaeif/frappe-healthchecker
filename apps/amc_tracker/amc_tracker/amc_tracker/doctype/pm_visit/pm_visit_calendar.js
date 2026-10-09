// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

// PM Calendar: PM Visit > Calendar. Each dated visit is shown (blue = scheduled, orange = completed,
// green = report submitted). "PM due" markers show AMCs whose engineers or visit dates are still missing.
// Drag a visit to move it. Filter by Engineer to also see that engineer's leave.
frappe.views.calendar["PM Visit"] = {
	field_map: {
		start: "start",
		end: "end",
		id: "name",
		title: "title",
		allDay: "allDay",
		color: "color",
		convertToUserTz: "convert_to_user_tz",
	},
	get_events_method: "amc_tracker.api.calendar.get_events",
	update_event_method: "amc_tracker.api.calendar.update_event",
	filters: [
		{
			fieldtype: "Link",
			fieldname: "engineer",
			options: "Engineer",
			label: __("Engineer"),
			get_query: () => ({ filters: { status: "Active" } }),
		},
		{ fieldtype: "Link", fieldname: "client", options: "Client", label: __("Client") },
	],
};
