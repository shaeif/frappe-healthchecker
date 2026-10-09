// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["HC Contact Log"] = {
	add_fields: ["outcome", "follow_up_on"],
	get_indicator(doc) {
		const good = ["Client confirmed date", "Booking request sent"];
		const bad = ["No answer", "Wrong contact details"];
		const color = good.includes(doc.outcome) ? "green" : bad.includes(doc.outcome) ? "red" : "orange";
		return [__(doc.outcome), color, `outcome,=,${doc.outcome}`];
	},
};
