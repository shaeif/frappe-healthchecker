// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.listview_settings["Client"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return doc.status === "Active" ? [__("Active"), "green", "status,=,Active"] : [__("Inactive"), "gray", "status,=,Inactive"];
	},
	onload(listview) {
		if (!(frappe.model.can_create("Client") && frappe.model.can_create("Data Import"))) return;
		listview.page.add_inner_button(
			__("Download Excel Template"),
			() => window.open("/api/method/amc_tracker.api.import_tools.download_import_template?doctype=Client"),
			__("Import")
		);
		listview.page.add_inner_button(
			__("Import from Excel"),
			() => frappe.new_doc("Data Import", { reference_doctype: "Client", import_type: "Insert New Records" }),
			__("Import")
		);
	},
};
