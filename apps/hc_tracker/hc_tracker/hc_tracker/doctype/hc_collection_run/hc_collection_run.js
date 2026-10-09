// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("HC Collection Run", {
	refresh(frm) {
		const colors = { Completed: "green", Partial: "orange", Failed: "red", Running: "blue", Queued: "gray" };
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");

		frm.add_custom_button(__("Open Contract"), () =>
			frappe.set_route("Form", "HC Contract", frm.doc.contract)
		);

		if (frm.doc.report_file && ["Completed", "Partial"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Use as Current Report"), () => {
				frappe.confirm(
					__("Attach this draft report as the contract's Current Report? The status changes to Report sent and the Account Manager is notified."),
					() =>
						frappe
							.xcall("hc_tracker.hc_tracker.doctype.hc_collection_run.hc_collection_run.use_as_current_report", {
								run: frm.doc.name,
							})
							.then((status) => {
								frappe.show_alert({ message: __("Contract status: {0}", [__(status)]), indicator: "green" });
								frappe.set_route("Form", "HC Contract", frm.doc.contract);
							})
				);
			}).addClass("btn-primary");
		}

		if (["Completed", "Partial", "Failed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Run Again"), () =>
				frappe
					.xcall("hc_tracker.collectors.jobs.enqueue_collection", { contract: frm.doc.contract })
					.then((name) => frappe.set_route("Form", "HC Collection Run", name))
			);
		}

		if (["Queued", "Running"].includes(frm.doc.status)) {
			frm.dashboard.set_headline_alert(__("Collection in progress. This page refreshes when it finishes."), "blue");
			frappe.realtime.off("hc_collection_done");
			frappe.realtime.on("hc_collection_done", (data) => {
				if (data && data.run === frm.doc.name) frm.reload_doc();
			});
		}
	},
});
