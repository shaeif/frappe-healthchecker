// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("AMC Notification Flow", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Rules are checked every working day at 08:00 (Asia/Qatar) and whenever a PM cycle or visit changes. " +
					"Each rule is sent once per cycle (once per visit for visit rules) unless Repeat Every is set."
			),
			"blue"
		);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Test Rules"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save before testing."));
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Test Rules (dry run - nothing is sent)"),
				size: "extra-large",
				fields: [
					{ fieldname: "amc", fieldtype: "Link", options: "AMC", label: __("AMC"), reqd: 1 },
					{ fieldtype: "Column Break" },
					{ fieldname: "on_date", fieldtype: "Date", label: __("Evaluate As Of"), default: frappe.datetime.get_today(), reqd: 1 },
					{ fieldtype: "Section Break" },
					{ fieldname: "result", fieldtype: "HTML" },
				],
				primary_action_label: __("Run Dry Run"),
				primary_action(values) {
					frappe.call({
						method: "amc_tracker.notifications.engine.dry_run",
						args: { flow: frm.doc.name, amc: values.amc, on_date: values.on_date },
						freeze: true,
						freeze_message: __("Evaluating rules..."),
						callback(r) {
							if (r.message) dialog.fields_dict.result.$wrapper.html(r.message.html);
						},
					});
				},
			});
			dialog.show();
		});

		frm.add_custom_button(__("Notification Log"), () =>
			frappe.set_route("List", "AMC Notification Log", { flow: frm.doc.name })
		);
	},
});

frappe.ui.form.on("AMC Notification Step", {
	steps_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const max = Math.max(0, ...(frm.doc.steps || []).map((s) => s.step_no || 0));
		frappe.model.set_value(cdt, cdn, "step_no", max + 1);
		if (!row.channel) frappe.model.set_value(cdt, cdn, "channel", "Email");
	},
	trigger_mode(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.trigger_mode !== "On cycle status change" && row.on_status) {
			frappe.model.set_value(cdt, cdn, "on_status", "");
		}
	},
});
