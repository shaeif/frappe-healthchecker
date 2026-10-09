// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

// Booking calendar: HC Contract > Calendar. Drag a grey/orange/red "Due" item onto a day to book it,
// drag a booked item to reschedule it. Filter by Assigned Engineer to also see that engineer's leave.
frappe.views.calendar["HC Contract"] = {
	field_map: {
		start: "start",
		end: "end",
		id: "name",
		title: "title",
		allDay: "allDay",
		color: "color",
		convertToUserTz: "convert_to_user_tz",
	},
	get_events_method: "hc_tracker.api.calendar.get_events",
	update_event_method: "hc_tracker.api.calendar.update_event",
	filters: [
		{
			fieldtype: "Link",
			fieldname: "assigned_engineer",
			options: "User",
			label: __("Assigned Engineer"),
		},
	],
};
