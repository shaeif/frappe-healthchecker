// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["Expertise"] = {
	add_fields: ["enabled"],
	get_indicator(doc) {
		return doc.enabled ? [__("Enabled"), "green", "enabled,=,1"] : [__("Disabled"), "gray", "enabled,=,0"];
	},
};
