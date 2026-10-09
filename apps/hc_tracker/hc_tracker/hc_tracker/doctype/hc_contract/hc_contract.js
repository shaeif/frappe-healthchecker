// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

const HC_ROLE_QUERY = "hc_tracker.api.queries.users_with_role";

frappe.ui.form.on("HC Contract", {
	setup(frm) {
		const by_role = (role) => () => ({ query: HC_ROLE_QUERY, filters: { role } });
		frm.set_query("assigned_engineer", by_role("HC Engineer"));
		frm.set_query("account_manager", by_role("HC Account Manager"));
		frm.set_query("helpdesk_contact", by_role("HC Helpdesk"));
		frm.set_query("technical_manager", by_role("HC Technical Manager"));
		frm.set_query("notification_flow", () => ({
			filters: {
				enabled: 1,
				applies_to_frequency: ["in", ["All", frm.doc.frequency || "All"]],
			},
		}));
	},

	refresh(frm) {
		hc_tracker_contract.show_due_banner(frm);
		hc_tracker_contract.render_timeline(frm);
		hc_tracker_contract.add_buttons(frm);
	},

	next_due_date(frm) {
		hc_tracker_contract.show_due_banner(frm);
	},

	status(frm) {
		if (frm.doc.status === "Signed off" && !frm.doc.current_report) {
			frappe.msgprint(__("Attach the HC report (Current Report) before signing off."));
		}
	},

	current_report(frm) {
		if (
			frm.doc.current_report &&
			["Not started", "Scheduled", "In progress"].includes(frm.doc.status)
		) {
			frappe.show_alert({
				message: __("Status will change to Report sent when you save."),
				indicator: "blue",
			});
		}
	},
});

const hc_tracker_contract = {
	show_due_banner(frm) {
		if (frm.is_new() || !frm.doc.next_due_date) return;
		const days = frappe.datetime.get_day_diff(
			frm.doc.next_due_date,
			frappe.datetime.get_today()
		);
		let text;
		let color;
		if (days < 0) {
			text = __("Overdue by {0} days", [Math.abs(days)]);
			color = "red";
		} else if (days === 0) {
			text = __("Due today");
			color = "orange";
		} else if (days <= 14) {
			text = __("Due in {0} days", [days]);
			color = "orange";
		} else {
			text = __("Due in {0} days", [days]);
			color = "green";
		}
		const due = frappe.datetime.str_to_user(frm.doc.next_due_date);
		frm.dashboard.set_headline_alert(
			`<div class="indicator ${color}"><b>${text}</b> &middot; ${__("Next due")}: ${due} &middot; ${__("Status")}: ${__(frm.doc.status)}</div>`,
			color
		);
	},

	render_timeline(frm) {
		const field = frm.get_field("notification_timeline");
		if (!field) return;
		const html =
			(frm.doc.__onload && frm.doc.__onload.notification_timeline) ||
			`<p class="text-muted">${__("Save the contract to see its notification timeline.")}</p>`;
		field.$wrapper.html(html);
	},

	add_buttons(frm) {
		if (frm.is_new()) return;
		const can_sign_off = frappe.user.has_role([
			"HC Account Manager",
			"HC Technical Manager",
			"System Manager",
		]);

		if (frm.doc.status === "Not started" && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Mark Scheduled"), () => {
				frappe.prompt(
					[
						{
							fieldname: "scheduled_date",
							fieldtype: "Date",
							label: __("Booked HC Date"),
							reqd: 1,
							default: frm.doc.scheduled_date,
						},
					],
					(values) => {
						frm.set_value("scheduled_date", values.scheduled_date);
						frm.set_value("status", "Scheduled");
						frm.save();
					},
					__("Book Health Check"),
					__("Mark Scheduled")
				);
			});
		}

		if (can_sign_off && frm.doc.status === "Report sent") {
			frm.add_custom_button(__("Sign Off Cycle"), () => {
				if (!frm.doc.current_report) {
					frappe.msgprint(__("Attach the HC report (Current Report) before signing off."));
					return;
				}
				frappe.confirm(
					__(
						"Sign off this cycle? The due date rolls forward by {0} month(s) and a new notification cycle starts.",
						[frm.doc.interval_months]
					),
					() => {
						frm.set_value("status", "Signed off");
						frm.save();
					}
				);
			});
		}

		frm.add_custom_button(
			__("Refresh Timeline"),
			() => frm.reload_doc(),
			__("Notifications")
		);
		frm.add_custom_button(
			__("Notification Log"),
			() => frappe.set_route("List", "HC Notification Log", { contract: frm.doc.name }),
			__("Notifications")
		);

		if (
			frappe.user.has_role(["HC Technical Manager", "System Manager"]) &&
			(frm.doc.devices || []).length
		) {
			frm.add_custom_button(
				__("Collect Device Data (Phase 2 stub)"),
				() =>
					frappe.call({
						method: "hc_tracker.collectors.jobs.enqueue_collection",
						args: { contract: frm.doc.name },
						callback: (r) => r.message && frappe.show_alert(r.message),
					}),
				__("Devices")
			);
		}
	},
};
