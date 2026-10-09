// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["HC Notification Log"] = {
	add_fields: ["status", "channel"],
	get_indicator(doc) {
		return doc.status === "Failed"
			? [__("Failed"), "red", "status,=,Failed"]
			: [__("Sent"), "green", "status,=,Sent"];
	},
};
