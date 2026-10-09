// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("PM Visit", {
	setup(frm) {
		frm.set_query("engineer", amc_tracker.engineer_query);
		frm.set_query("amc", () => ({ filters: { status: "Active" } }));
		frm.set_query("expertise_covered", () => {
			const known = frm.__expertise || [];
			return { filters: known.length ? { name: ["in", known] } : { enabled: 1 } };
		});
	},

	engineer(frm) {
		amc_tracker.expertise_of(frm.doc.engineer).then((list) => (frm.__expertise = list));
	},

	refresh(frm) {
		amc_tracker.expertise_of(frm.doc.engineer).then((list) => (frm.__expertise = list));
		pm_visit_form.banner(frm);
		pm_visit_form.buttons(frm);
		frm.toggle_enable(["amc", "engineer"], frm.is_new() || amc_tracker.is_helpdesk());
		if (!frm.is_new() && !amc_tracker.is_helpdesk() && !amc_tracker.is_manager() && frm.doc.engineer !== frappe.session.user) {
			frm.disable_save();
			frm.set_intro(__("This visit belongs to {0}. You can view it but not change it.", [frm.doc.engineer_name || frm.doc.engineer]), "blue");
		}
	},

	onload_post_render(frm) {
		frm.__amc_saved_date = frm.doc.visit_date;
	},

	after_save(frm) {
		frm.__amc_saved_date = frm.doc.visit_date;
	},

	visit_date(frm) {
		if (!frm.is_new() && frm.__amc_saved_date && frm.doc.visit_date && frm.doc.visit_date !== frm.__amc_saved_date && !frm.doc.reschedule_reason) {
			amc_tracker.ask_reschedule_reason(frm);
		}
	},

	report(frm) {
		if (frm.doc.report) {
			frappe.show_alert({ message: __("The visit becomes 'Report submitted' when you save."), indicator: "blue" });
		}
	},
});

const pm_visit_form = {
	banner(frm) {
		if (frm.is_new()) return;
		const color = amc_tracker.status_color(frm.doc.status);
		let text = `<b>${__(frm.doc.status)}</b>`;
		if (frm.doc.visit_date) {
			text += ` &middot; ${__("Visit")}: ${frappe.datetime.str_to_user(frm.doc.visit_date)} (${__(frm.doc.visit_mode || "")})`;
		} else if (frm.doc.status === "To be scheduled") {
			text += ` &middot; ${__("Agree a date with the client and click Set Visit Date.")}`;
		}
		if (frm.doc.due_date) text += ` &middot; ${__("PM due")}: ${frappe.datetime.str_to_user(frm.doc.due_date)}`;
		frm.dashboard.set_headline_alert(`<div class="indicator ${color}">${text}</div>`, color);
	},

	buttons(frm) {
		if (frm.is_new()) return;
		const doc = frm.doc;
		// Engineers may only plan and report their own visits (enforced on the server too)
		const can_write =
			frm.perm[0] && frm.perm[0].write && (amc_tracker.is_helpdesk() || amc_tracker.is_manager() || doc.engineer === frappe.session.user);
		const open = !["Cancelled", "Report submitted"].includes(doc.status);
		if (can_write && open) {
			frm.add_custom_button(doc.visit_date ? __("Reschedule") : __("Set Visit Date"), () => amc_tracker.visit_date_dialog(frm)).addClass(
				doc.visit_date ? "" : "btn-primary"
			);
		}
		if (can_write && doc.status === "Scheduled") {
			frm.add_custom_button(__("Mark Completed"), () =>
				frappe.prompt(
					{ fieldname: "completed_on", fieldtype: "Date", label: __("Completed On"), default: doc.visit_date > frappe.datetime.get_today() ? frappe.datetime.get_today() : doc.visit_date, reqd: 1 },
					(v) => frappe.xcall("amc_tracker.amc_tracker.doctype.pm_visit.pm_visit.mark_completed", { name: doc.name, completed_on: v.completed_on }).then(() => frm.reload_doc()),
					__("Mark Completed")
				)
			);
		}
		const group = __("Client");
		frm.add_custom_button(__("Email Client to Schedule"), () => amc_tracker.scheduling_email_dialog(doc.amc, doc.name, () => frm.reload_doc()), group);
		frm.add_custom_button(__("Log Client Contact"), () => amc_tracker.contact_dialog(doc.amc, doc.name, null, () => frm.reload_doc()), group);
		frm.add_custom_button(__("Open AMC"), () => frappe.set_route("Form", "AMC", doc.amc), group);

		if (amc_tracker.is_helpdesk() && can_write) {
			if (open) {
				frm.add_custom_button(
					__("Cancel Visit"),
					() =>
						frappe.prompt(
							{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
							(v) => frappe.xcall("amc_tracker.amc_tracker.doctype.pm_visit.pm_visit.cancel_visit", { name: doc.name, reason: v.reason }).then(() => frm.reload_doc()),
							__("Cancel this PM visit?")
						),
					__("Helpdesk")
				);
			} else if (doc.status === "Cancelled") {
				frm.add_custom_button(
					__("Reopen Visit"),
					() => frappe.xcall("amc_tracker.amc_tracker.doctype.pm_visit.pm_visit.reopen_visit", { name: doc.name }).then(() => frm.reload_doc()),
					__("Helpdesk")
				);
			}
		}
	},
};
