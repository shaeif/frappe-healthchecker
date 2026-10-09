// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["PM Visit"] = {
	add_fields: ["status", "visit_date", "visit_mode"],
	get_indicator(doc) {
		const map = {
			"To be scheduled": "orange",
			Scheduled: "blue",
			Completed: "purple",
			"Report submitted": "green",
			Cancelled: "gray",
		};
		if (doc.status === "Scheduled" && doc.visit_date && doc.visit_date < frappe.datetime.get_today()) {
			return [__("Report pending"), "red", `visit_date,<,${frappe.datetime.get_today()}`];
		}
		return [__(doc.status), map[doc.status] || "gray", `status,=,${doc.status}`];
	},
	onload(listview) {
		listview.page.add_inner_button(__("PM Calendar"), () => frappe.set_route("List", "PM Visit", "Calendar", "default"));
		if (frappe.user.has_role("AMC Engineer") && !frappe.user.has_role(["AMC Helpdesk", "AMC Technical Manager", "AMC Account Manager"])) {
			listview.page.add_inner_button(__("Only My Visits"), () => {
				listview.filter_area.add([[listview.doctype, "engineer", "=", frappe.session.user]]);
			});
		}
	},
};
