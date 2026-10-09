// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["AMC Notification Flow"] = {
	add_fields: ["enabled", "is_default", "applies_to_frequency"],
	get_indicator(doc) {
		if (!doc.enabled) return [__("Disabled"), "gray", "enabled,=,0"];
		if (doc.is_default) return [__("Default"), "blue", "is_default,=,1"];
		return [__(doc.applies_to_frequency), "green", `applies_to_frequency,=,${doc.applies_to_frequency}`];
	},
};
