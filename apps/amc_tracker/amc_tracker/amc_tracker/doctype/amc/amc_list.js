// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["AMC"] = {
	add_fields: ["status", "next_due_date", "cycle_status", "contract_end"],
	get_indicator(doc) {
		const today = frappe.datetime.get_today();
		if (doc.status !== "Active") return [__(doc.status), "gray", `status,=,${doc.status}`];
		if (doc.contract_end && doc.contract_end < today) return [__("Contract ended"), "gray", `contract_end,<,${today}`];
		if (!doc.next_due_date) return [__("No due date"), "gray", "next_due_date,is,not set"];
		const days = frappe.datetime.get_day_diff(doc.next_due_date, today);
		if (days < 0) return [__("Overdue {0}d", [Math.abs(days)]), "red", `next_due_date,<,${today}`];
		if (doc.cycle_status === "Reports submitted") return [__("Ready for sign-off"), "green", "cycle_status,=,Reports submitted"];
		if (days <= 14) return [__("Due in {0}d", [days]), "orange", `next_due_date,<=,${frappe.datetime.add_days(today, 14)}`];
		return [__(doc.cycle_status || "Not started"), "blue", `cycle_status,=,${doc.cycle_status}`];
	},
	onload(listview) {
		amc_tracker_import_buttons(listview, "AMC");
		listview.page.add_inner_button(__("PM Calendar"), () => frappe.set_route("List", "PM Visit", "Calendar", "default"));
	},
};

function amc_tracker_import_buttons(listview, doctype) {
	if (!(frappe.model.can_create(doctype) && frappe.model.can_create("Data Import"))) return;
	listview.page.add_inner_button(
		__("Download Excel Template"),
		() => window.open(`/api/method/amc_tracker.api.import_tools.download_import_template?doctype=${encodeURIComponent(doctype)}`),
		__("Import")
	);
	listview.page.add_inner_button(
		__("Import from Excel"),
		() => frappe.new_doc("Data Import", { reference_doctype: doctype, import_type: "Insert New Records" }),
		__("Import")
	);
}
