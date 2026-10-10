// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

// PM Calendar: PM Visit > Calendar. Each dated visit is shown (blue = scheduled, orange = completed,
// green = report submitted). "PM due" markers show AMCs whose engineers or visit dates are still missing;
// clicking one opens the AMC.
// Drag a visit to move it. Filter by Engineer to also see that engineer's leave.
if (!document.getElementById("amc-pm-calendar-style")) {
	const style = document.createElement("style");
	style.id = "amc-pm-calendar-style";
	style.textContent = ".fc-event.fc-event-past.amc-needs-action { opacity: 1; }";
	document.head.appendChild(style);
}

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
	options: {
		// Only visits are PM Visit documents: "PM due::<AMC>" opens the AMC, holidays and leave open nothing.
		eventClick(info) {
			const id = info.event.id || "";
			if (id.startsWith("due::")) {
				frappe.set_route("Form", "AMC", id.slice("due::".length));
			} else if (!id.includes("::")) {
				frappe.set_route("Form", "PM Visit", id);
			}
		},
	},
	// Frappe makes every event draggable when the user can write PM Visit; only visits can be moved.
	// Frappe also fades past events; overdue "PM due" markers and past visits still Scheduled need action,
	// so they stay at full strength.
	prepare_events(events) {
		return frappe.views.Calendar.prototype.prepare_events.call(this, events).map((d) => {
			const name = String(d.name);
			if (name.includes("::")) d.editable = false;
			if (name.startsWith("due::") || d.status === "Scheduled") {
				d.classNames = (d.classNames || []).concat("amc-needs-action");
			}
			return d;
		});
	},
	// Frappe v16 draws every event as a faint tint of its colour, so visits barely stood out.
	// Show visits and "PM due" markers in their full status colour; holidays and leave stay shaded.
	prepare_colors(d) {
		const color = d.color || "#2490ef";
		d.backgroundColor = color;
		if (d.display !== "background") {
			d.borderColor = color;
			d.textColor = "#ffffff";
		}
		return d;
	},
};
