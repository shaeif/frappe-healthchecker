// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["HC Contract"] = {
	add_fields: ["status", "next_due_date", "last_hc_date", "contract_end", "frequency"],
	hide_name_column: true,

	get_indicator(doc) {
		const today = frappe.datetime.get_today();

		if (doc.status === "Signed off") {
			return [__("Signed off"), "gray", "status,=,Signed off"];
		}
		if (doc.contract_end && doc.contract_end < today) {
			return [__("Contract ended"), "gray", `contract_end,<,${today}`];
		}
		if (!doc.next_due_date) {
			return [__(doc.status || "Not started"), "gray", "next_due_date,is,not set"];
		}

		const days = frappe.datetime.get_day_diff(doc.next_due_date, today);
		if (days < 0) {
			return [__("Overdue {0}d", [Math.abs(days)]), "red", `next_due_date,<,${today}`];
		}
		const in_14 = frappe.datetime.add_days(today, 14);
		if (days <= 14) {
			return [__("Due in {0}d", [days]), "orange", `next_due_date,<=,${in_14}`];
		}
		// Recently signed off (the cycle was closed in the last 14 days)
		if (doc.last_hc_date && frappe.datetime.get_day_diff(today, doc.last_hc_date) <= 14) {
			return [__("Signed off"), "gray", `last_hc_date,>=,${frappe.datetime.add_days(today, -14)}`];
		}
		return [__(doc.status || "On track"), "green", `next_due_date,>,${in_14}`];
	},
};
