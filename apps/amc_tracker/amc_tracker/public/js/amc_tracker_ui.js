// AMC Tracker: dialogs shared by the AMC and PM Visit forms.
// Loaded on every desk page via hooks.app_include_js (plain file, no bundling needed).

(function () {
	if (window.amc_tracker) return;

	const ROLE_QUERY = "amc_tracker.api.queries.users_with_role";
	const RESCHEDULE_REASONS = ["Client request", "Engineer unavailable", "Access / change-freeze window", "Public holiday", "Other"];
	const OUTCOMES = [
		"No answer",
		"Left voicemail",
		"Scheduling email sent",
		"Client will confirm",
		"Client confirmed date",
		"Client asked for later date",
		"Wrong contact details",
		"Other",
	];
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

	window.amc_tracker = {
		ROLE_QUERY,
		RESCHEDULE_REASONS,
		OUTCOMES,
		esc,

		engineer_query() {
			return { filters: { status: "Active" } };
		},

		expertise_of(engineer) {
			if (!engineer) return Promise.resolve([]);
			return frappe.xcall("amc_tracker.amc_tracker.doctype.engineer.engineer.expertise_of", { engineer });
		},

		is_admin() {
			return frappe.user.has_role(["System Manager", "AMC Admin"]);
		},

		is_manager() {
			return frappe.user.has_role(["System Manager", "AMC Admin", "AMC Technical Manager", "AMC Account Manager"]);
		},

		is_helpdesk() {
			return frappe.user.has_role(["System Manager", "AMC Admin", "AMC Technical Manager", "AMC Helpdesk"]);
		},

		// Hand an engineer's place on an AMC (rows + open visit of the current cycle) to another engineer.
		// team: engineers the helpdesk may pick from; an engineer only transfers their own place.
		transfer_dialog(amc, { from_engineer, team, after } = {}) {
			const on_behalf = amc_tracker.is_helpdesk() && (team || []).length;
			const from = () => (on_behalf ? d.get_value("from_engineer") : from_engineer || frappe.session.user);
			const d = new frappe.ui.Dialog({
				title: __("Transfer to Another Engineer"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="text-muted small">${__(
							"The new engineer takes over the AMC rows and the visit of the current cycle that is not done yet. Completed and reported visits stay with the original engineer."
						)}</p>`,
					},
					on_behalf
						? {
								fieldname: "from_engineer",
								fieldtype: "Select",
								label: __("From Engineer"),
								options: team.map((e) => ({ value: e.engineer, label: e.engineer_name || e.engineer })),
								default: from_engineer || team[0].engineer,
								reqd: 1,
						  }
						: null,
					{
						fieldname: "to_engineer",
						fieldtype: "Link",
						options: "Engineer",
						label: __("Transfer To"),
						reqd: 1,
						get_query: () => ({ filters: { status: "Active", name: ["!=", from()] } }),
					},
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					{
						fieldname: "keep_visit_date",
						fieldtype: "Check",
						label: __("Keep the agreed visit date"),
						default: 1,
						description: __("Untick to let the new engineer set a new date with the client."),
					},
				].filter(Boolean),
				primary_action_label: __("Transfer"),
				primary_action(values) {
					frappe
						.xcall("amc_tracker.cycle.transfer_engineer", {
							amc,
							from_engineer: from(),
							to_engineer: values.to_engineer,
							reason: values.reason,
							keep_visit_date: values.keep_visit_date,
						})
						.then(() => {
							d.hide();
							frappe.show_alert({ message: __("Transferred."), indicator: "green" });
							after && after(values);
						});
				},
			});
			d.show();
		},

		status_color(status) {
			return (
				{
					"Not started": "gray",
					"Engineers assigned": "orange",
					"To be scheduled": "orange",
					Scheduled: "blue",
					"In progress": "purple",
					Completed: "purple",
					"Reports submitted": "green",
					"Report submitted": "green",
					Cancelled: "gray",
				}[status] || "gray"
			);
		},

		pill(status) {
			return `<span class="indicator-pill ${this.status_color(status)}">${esc(__(status))}</span>`;
		},

		availability_html(res) {
			let html = "";
			if (res.problems && res.problems.length) {
				html += `<div class="alert alert-${res.blocking ? "danger" : "warning"}" style="margin-bottom:8px">
					<b>${res.blocking ? __("Not available") : __("Check this date")}</b><br>
					${res.problems.map((p) => esc(p.message)).join("<br>")}</div>`;
			} else {
				html += `<div class="text-success" style="margin-bottom:8px">${__("Engineer available and working day.")}</div>`;
			}
			if (res.week && res.week.length) {
				html += `<div class="text-muted small">${__("Other visits that week")}: ${res.week
					.map((w) => `${esc(w.client)} (${esc(w.date)}, ${esc(w.mode)})`)
					.join(", ")}</div>`;
			}
			return html;
		},

		// Engineer picks / changes the visit date (with live availability check)
		visit_date_dialog(frm) {
			const doc = frm.doc;
			const rescheduling = !!doc.visit_date;
			const d = new frappe.ui.Dialog({
				title: rescheduling ? __("Reschedule PM Visit") : __("Set Visit Date"),
				fields: [
					{ fieldname: "visit_date", fieldtype: "Date", label: __("Visit Date"), reqd: 1, default: doc.visit_date },
					{ fieldname: "visit_mode", fieldtype: "Select", label: __("Visit Mode"), options: ["On-site", "Remote"], default: doc.visit_mode || "On-site" },
					{ fieldtype: "Column Break" },
					{ fieldname: "start_time", fieldtype: "Time", label: __("From"), default: doc.start_time },
					{ fieldname: "end_time", fieldtype: "Time", label: __("To"), default: doc.end_time },
					{ fieldtype: "Section Break" },
					{ fieldname: "availability", fieldtype: "HTML" },
					{
						fieldname: "reschedule_reason",
						fieldtype: "Select",
						label: __("Reschedule Reason"),
						options: ["", ...RESCHEDULE_REASONS],
						reqd: rescheduling ? 1 : 0,
						hidden: rescheduling ? 0 : 1,
					},
					{ fieldname: "reschedule_note", fieldtype: "Small Text", label: __("Note"), hidden: rescheduling ? 0 : 1 },
				],
				primary_action_label: rescheduling ? __("Reschedule") : __("Save Date"),
				primary_action(values) {
					d.hide();
					frm.__amc_saved_date = values.visit_date;
					frm.set_value({
						visit_date: values.visit_date,
						visit_mode: values.visit_mode,
						start_time: values.start_time || null,
						end_time: values.end_time || null,
						reschedule_reason: rescheduling ? values.reschedule_reason : null,
						reschedule_note: rescheduling ? values.reschedule_note || "" : null,
					}).then(() => frm.save());
				},
			});
			const check = () => {
				const date = d.get_value("visit_date");
				if (!date) return;
				frappe
					.xcall("amc_tracker.scheduling.get_availability", { engineer: doc.engineer, date, visit: doc.name })
					.then((res) => d.fields_dict.availability.$wrapper.html(amc_tracker.availability_html(res)));
			};
			d.fields_dict.visit_date.df.onchange = check;
			d.show();
			check();
		},

		ask_reschedule_reason(frm) {
			frappe.prompt(
				[
					{ fieldname: "reason", fieldtype: "Select", label: __("Reschedule Reason"), options: RESCHEDULE_REASONS, reqd: 1 },
					{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
				],
				(values) => frm.set_value({ reschedule_reason: values.reason, reschedule_note: values.note || "" }),
				__("Why is the visit date changing?"),
				__("OK")
			);
		},

		// Email to the client to agree a date (from the AMC, or from one PM visit)
		scheduling_email_dialog(amc, visit, after) {
			const d = new frappe.ui.Dialog({
				title: __("Email Client to Schedule the PM"),
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
						.xcall("amc_tracker.api.scheduling_email.send_scheduling_email", {
							amc,
							visit,
							recipients: values.recipients,
							cc: values.cc,
							subject: values.subject,
							message: values.message,
						})
						.then(() => {
							d.hide();
							frappe.show_alert({ message: __("Email sent and logged."), indicator: "green" });
							after && after();
						});
				},
			});
			const fill = () => {
				const dates = ["date_1", "date_2", "date_3"].map((f) => d.get_value(f)).filter(Boolean);
				frappe
					.xcall("amc_tracker.api.scheduling_email.get_scheduling_email", { amc, visit, proposed_dates: dates })
					.then((r) => {
						if (!d.get_value("recipients")) d.set_value("recipients", r.recipients);
						if (!d.get_value("cc")) d.set_value("cc", r.cc);
						d.set_value("subject", r.subject);
						d.set_value("message", r.message);
						if (!r.recipients) {
							frappe.show_alert({ message: __("Tip: save the contact email on the Client."), indicator: "orange" });
						}
					});
			};
			["date_1", "date_2", "date_3"].forEach((f) => (d.fields_dict[f].df.onchange = fill));
			d.show();
			fill();
		},

		contact_dialog(amc, visit, preferred, after) {
			const d = new frappe.ui.Dialog({
				title: __("Log Client Contact"),
				fields: [
					{ fieldname: "method", fieldtype: "Select", label: __("Method"), options: ["Phone", "Email", "Teams", "WhatsApp", "In person"], default: preferred || "Phone" },
					{ fieldname: "direction", fieldtype: "Select", label: __("Direction"), options: ["Outgoing", "Incoming"], default: "Outgoing" },
					{ fieldname: "outcome", fieldtype: "Select", label: __("Outcome"), options: OUTCOMES, reqd: 1 },
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
						.xcall("amc_tracker.amc_tracker.doctype.client_contact_log.client_contact_log.log_contact", {
							amc,
							pm_visit: visit,
							...values,
						})
						.then(() => {
							d.hide();
							frappe.show_alert({ message: __("Contact logged."), indicator: "green" });
							after && after(values);
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

	// Resizing a list column saves List View Settings and Property Setters for every user, which only
	// System Manager may write; anyone else (AMC Admin included) got "No permission for List View
	// Settings". Keep the new width on screen for them and skip the save, like the List Settings menu.
	const ListView = frappe.views && frappe.views.ListView;
	if (ListView && ListView.prototype.save_column_width) {
		const save_column_width = ListView.prototype.save_column_width;
		ListView.prototype.save_column_width = function (...args) {
			if (!frappe.user.has_role("System Manager")) return;
			return save_column_width.apply(this, args);
		};
	}
})();
