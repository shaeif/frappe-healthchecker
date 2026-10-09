// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["HC Collection Run"] = {
	add_fields: ["status", "critical_count"],
	get_indicator(doc) {
		const colors = { Completed: "green", Partial: "orange", Failed: "red", Running: "blue", Queued: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
