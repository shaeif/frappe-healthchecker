// Copyright (c) 2026, HC Tracker Maintainers and contributors
// For license information, please see license.txt

const HC_ROLE_QUERY = "hc_tracker.api.queries.users_with_role";
const HC_RESCHEDULE_REASONS = [
	"Client request",
	"Engineer unavailable",
	"Access / change-freeze window",
	"Public holiday",
	"Other",
];
const HC_OUTCOMES = [
	"No answer",
	"Left voicemail",
	"Booking request sent",
	"Client will confirm",
	"Client confirmed date",
	"Client asked for later date",
	"Wrong contact details",
	"Other",
];

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

	scheduled_date(frm) {
		// A booked date changed in the form: ask why (recorded in Reschedule History)
		if (
			!frm.is_new() &&
			frm.__hc_saved_date &&
			frm.doc.scheduled_date &&
			frm.doc.scheduled_date !== frm.__hc_saved_date &&
			!frm.doc.reschedule_reason
		) {
			hc_tracker_contract.ask_reschedule_reason(frm);
		}
	},

	onload_post_render(frm) {
		frm.__hc_saved_date = frm.doc.scheduled_date;
	},

	after_save(frm) {
		frm.__hc_saved_date = frm.doc.scheduled_date;
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
		const days = frappe.datetime.get_day_diff(frm.doc.next_due_date, frappe.datetime.get_today());
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
		let extra = "";
		if (frm.doc.scheduled_date) {
			extra += ` &middot; ${__("Booked")}: ${frappe.datetime.str_to_user(frm.doc.scheduled_date)}`;
		}
		if (
			frm.doc.reminders_paused_until &&
			frm.doc.reminders_paused_until > frappe.datetime.get_today()
		) {
			extra += ` &middot; <b>${__("Reminders paused until {0}", [
				frappe.datetime.str_to_user(frm.doc.reminders_paused_until),
			])}</b>`;
		}
		frm.dashboard.set_headline_alert(
			`<div class="indicator ${color}"><b>${text}</b> &middot; ${__("Next due")}: ${due} &middot; ${__("Status")}: ${__(frm.doc.status)}${extra}</div>`,
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

	can_write(frm) {
		return frm.perm[0] && frm.perm[0].write;
	},

	add_buttons(frm) {
		if (frm.is_new()) return;
		const can_sign_off = frappe.user.has_role(["HC Account Manager", "HC Technical Manager", "System Manager"]);

		if (["Not started", "Scheduled"].includes(frm.doc.status) && this.can_write(frm)) {
			const label = frm.doc.status === "Not started" ? __("Book Health Check") : __("Reschedule");
			frm.add_custom_button(label, () => this.booking_dialog(frm), __("Helpdesk"));
		}
		if (["Not started", "Scheduled"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Send Booking Request"), () => this.booking_request_dialog(frm), __("Helpdesk"));
		}
		frm.add_custom_button(__("Log Contact Attempt"), () => this.contact_dialog(frm), __("Helpdesk"));
		frm.add_custom_button(
			__("Contact History"),
			() => frappe.set_route("List", "HC Contact Log", { contract: frm.doc.name }),
			__("Helpdesk")
		);
		frm.add_custom_button(
			__("Booking Calendar"),
			() => frappe.set_route("List", "HC Contract", "Calendar", "default"),
			__("Helpdesk")
		);

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

		frm.add_custom_button(__("Refresh Timeline"), () => frm.reload_doc(), __("Notifications"));
		frm.add_custom_button(
			__("Notification Log"),
			() => frappe.set_route("List", "HC Notification Log", { contract: frm.doc.name }),
			__("Notifications")
		);
	},

	availability_html(res) {
		let html = "";
		if (res.problems && res.problems.length) {
			html += `<div class="alert alert-${res.blocking ? "danger" : "warning"}" style="margin-bottom:8px">
				<b>${res.blocking ? __("Not available") : __("Check before booking")}</b><br>
				${res.problems.map((p) => frappe.utils.escape_html(p.message)).join("<br>")}</div>`;
		} else {
			html += `<div class="text-success" style="margin-bottom:8px">${__("Engineer available and working day.")}</div>`;
		}
		if (res.week && res.week.length) {
			html += `<div class="text-muted small">${__("Engineer bookings that week")}: ${res.week
				.map((w) => `${frappe.utils.escape_html(w.client)} (${w.date})`)
				.join(", ")}</div>`;
		}
		return html;
	},

	booking_dialog(frm) {
		const rescheduling = frm.doc.status === "Scheduled" && frm.doc.scheduled_date;
		const d = new frappe.ui.Dialog({
			title: rescheduling ? __("Reschedule Health Check") : __("Book Health Check"),
			fields: [
				{ fieldname: "scheduled_date", fieldtype: "Date", label: __("Booked HC Date"), reqd: 1, default: frm.doc.scheduled_date },
				{ fieldname: "availability", fieldtype: "HTML" },
				{
					fieldname: "reschedule_reason",
					fieldtype: "Select",
					label: __("Reschedule Reason"),
					options: ["", ...HC_RESCHEDULE_REASONS],
					reqd: rescheduling ? 1 : 0,
					hidden: rescheduling ? 0 : 1,
				},
				{ fieldname: "reschedule_note", fieldtype: "Small Text", label: __("Note"), hidden: rescheduling ? 0 : 1 },
			],
			primary_action_label: rescheduling ? __("Reschedule") : __("Book"),
			primary_action(values) {
				d.hide();
				if (rescheduling) {
					frm.set_value("reschedule_reason", values.reschedule_reason);
					frm.set_value("reschedule_note", values.reschedule_note || "");
				}
				frm.__hc_saved_date = values.scheduled_date;
				frm.set_value("scheduled_date", values.scheduled_date);
				if (frm.doc.status === "Not started") frm.set_value("status", "Scheduled");
				frm.save();
			},
		});
		const check = () => {
			const date = d.get_value("scheduled_date");
			if (!date) return;
			frappe
				.xcall("hc_tracker.scheduling.get_availability", {
					engineer: frm.doc.assigned_engineer,
					date,
					contract: frm.doc.name,
				})
				.then((res) => d.fields_dict.availability.$wrapper.html(this.availability_html(res)));
		};
		d.fields_dict.scheduled_date.df.onchange = check;
		d.show();
		check();
	},

	ask_reschedule_reason(frm) {
		frappe.prompt(
			[
				{ fieldname: "reason", fieldtype: "Select", label: __("Reschedule Reason"), options: HC_RESCHEDULE_REASONS, reqd: 1 },
				{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
			],
			(values) => {
				frm.set_value("reschedule_reason", values.reason);
				frm.set_value("reschedule_note", values.note || "");
			},
			__("Why is the booked date changing?"),
			__("OK")
		);
	},

	booking_request_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Send Booking Request to Client"),
			size: "large",
			fields: [
				{ fieldname: "recipients", fieldtype: "Data", label: __("To"), reqd: 1 },
				{ fieldname: "cc", fieldtype: "Data", label: __("CC") },
				{ fieldtype: "Section Break", label: __("Proposed dates (optional)") },
				{ fieldname: "date_1", fieldtype: "Date", label: __("Option 1") },
				{ fieldtype: "Column Break" },
				{ fieldname: "date_2", fieldtype: "Date", label: __("Option 2") },
				{ fieldtype: "Column Break" },
				{ fieldname: "date_3", fieldtype: "Date", label: __("Option 3") },
				{ fieldtype: "Section Break" },
				{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1 },
				{ fieldname: "message", fieldtype: "Text Editor", label: __("Message"), reqd: 1 },
			],
			primary_action_label: __("Send"),
			primary_action(values) {
				frappe
					.xcall("hc_tracker.api.booking.send_booking_request", {
						contract: frm.doc.name,
						recipients: values.recipients,
						cc: values.cc,
						subject: values.subject,
						message: values.message,
					})
					.then(() => {
						d.hide();
						frappe.show_alert({ message: __("Booking request sent and logged."), indicator: "green" });
						frm.reload_doc();
					});
			},
		});
		const fill = () => {
			const dates = ["date_1", "date_2", "date_3"].map((f) => d.get_value(f)).filter(Boolean);
			frappe
				.xcall("hc_tracker.api.booking.get_booking_request", { contract: frm.doc.name, proposed_dates: dates })
				.then((r) => {
					if (!d.get_value("recipients")) d.set_value("recipients", r.recipients);
					if (!d.get_value("cc")) d.set_value("cc", r.cc);
					d.set_value("subject", r.subject);
					d.set_value("message", r.message);
				});
		};
		["date_1", "date_2", "date_3"].forEach((f) => (d.fields_dict[f].df.onchange = fill));
		d.show();
		fill();
		if (!frm.doc.client_contact_email) {
			frappe.show_alert({ message: __("Tip: save the client contact email on the contract."), indicator: "orange" });
		}
	},

	contact_dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Log Contact Attempt"),
			fields: [
				{ fieldname: "method", fieldtype: "Select", label: __("Method"), options: ["Phone", "Email", "Teams", "WhatsApp", "In person"], default: frm.doc.preferred_contact_method || "Phone" },
				{ fieldname: "direction", fieldtype: "Select", label: __("Direction"), options: ["Outgoing", "Incoming"], default: "Outgoing" },
				{ fieldname: "outcome", fieldtype: "Select", label: __("Outcome"), options: HC_OUTCOMES, reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "proposed_date", fieldtype: "Date", label: __("Date Proposed / Confirmed") },
				{ fieldname: "follow_up_on", fieldtype: "Date", label: __("Follow Up On") },
				{ fieldname: "pause_reminders_until", fieldtype: "Date", label: __("Pause Reminders Until") },
				{ fieldtype: "Section Break" },
				{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
			],
			primary_action_label: __("Save"),
			primary_action(values) {
				frappe
					.xcall("hc_tracker.hc_tracker.doctype.hc_contact_log.hc_contact_log.log_contact", {
						contract: frm.doc.name,
						...values,
					})
					.then(() => {
						d.hide();
						frappe.show_alert({ message: __("Contact logged."), indicator: "green" });
						if (
							values.outcome === "Client confirmed date" &&
							values.proposed_date &&
							frm.doc.status === "Not started" &&
							hc_tracker_contract.can_write(frm)
						) {
							frappe.confirm(
								__("Book the health check on {0} now?", [frappe.datetime.str_to_user(values.proposed_date)]),
								() => {
									frm.reload_doc().then(() => {
										frm.set_value("scheduled_date", values.proposed_date);
										frm.set_value("status", "Scheduled");
										frm.save();
									});
								},
								() => frm.reload_doc()
							);
						} else {
							frm.reload_doc();
						}
					});
			},
		});
		d.fields_dict.outcome.df.onchange = () => {
			const outcome = d.get_value("outcome");
			if (outcome === "Client asked for later date" && !d.get_value("pause_reminders_until")) {
				d.set_value("pause_reminders_until", frappe.datetime.add_days(frappe.datetime.get_today(), 14));
			}
			if (["No answer", "Left voicemail", "Client will confirm"].includes(outcome) && !d.get_value("follow_up_on")) {
				d.set_value("follow_up_on", frappe.datetime.add_days(frappe.datetime.get_today(), 2));
			}
		};
		d.show();
	},
};
