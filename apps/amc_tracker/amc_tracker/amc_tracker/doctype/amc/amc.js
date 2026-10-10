// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

frappe.ui.form.on("AMC", {
	setup(frm) {
		const by_role = (role) => () => ({ query: amc_tracker.ROLE_QUERY, filters: { role } });
		frm.set_query("account_manager", by_role("AMC Account Manager"));
		frm.set_query("technical_manager", by_role("AMC Technical Manager"));
		frm.set_query("helpdesk_contact", by_role("AMC Helpdesk"));
		frm.set_query("engineer", "engineers", amc_tracker.engineer_query);
		frm.set_query("expertise", "engineers", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const known = (frm.__expertise && frm.__expertise[row.engineer]) || [];
			return { filters: known.length ? { name: ["in", known] } : { enabled: 1 } };
		});
		frm.set_query("notification_flow", () => ({
			filters: { enabled: 1, applies_to_frequency: ["in", ["All", frm.doc.frequency || "All"]] },
		}));
	},

	refresh(frm) {
		amc_form.banner(frm);
		amc_form.render_timeline(frm);
		amc_form.render_visits(frm);
		amc_form.buttons(frm);
	},

	next_due_date(frm) {
		amc_form.banner(frm);
	},
});

const amc_form = {
	banner(frm) {
		if (frm.is_new() || !frm.doc.next_due_date) return;
		const days = frappe.datetime.get_day_diff(frm.doc.next_due_date, frappe.datetime.get_today());
		let text, color;
		if (frm.doc.status !== "Active") {
			text = __("Contract {0}", [__(frm.doc.status)]);
			color = "gray";
		} else if (days < 0) {
			text = __("PM overdue by {0} days", [Math.abs(days)]);
			color = "red";
		} else if (days === 0) {
			text = __("PM due today");
			color = "orange";
		} else {
			text = __("PM due in {0} days", [days]);
			color = days <= 14 ? "orange" : "green";
		}
		let extra = ` &middot; ${__("Cycle")} ${amc_tracker.esc(frm.doc.cycle_label || "")}:&nbsp;<b>${__(frm.doc.cycle_status || "Not started")}</b>`;
		if (frm.doc.reminders_paused_until && frm.doc.reminders_paused_until > frappe.datetime.get_today()) {
			extra += ` &middot; <b>${__("Reminders paused until {0}", [frappe.datetime.str_to_user(frm.doc.reminders_paused_until)])}</b>`;
		}
		frm.dashboard.set_headline_alert(
			`<div class="indicator ${color}"><b>${text}</b> &middot; ${__("Due")}: ${frappe.datetime.str_to_user(frm.doc.next_due_date)}${extra}</div>`,
			color
		);
	},

	render_timeline(frm) {
		const field = frm.get_field("notification_timeline");
		if (!field) return;
		field.$wrapper.html(
			(frm.doc.__onload && frm.doc.__onload.notification_timeline) ||
				`<p class="text-muted">${__("Save the AMC to see its notification timeline.")}</p>`
		);
	},

	render_visits(frm) {
		const field = frm.get_field("visits_html");
		if (!field) return;
		if (frm.is_new()) {
			field.$wrapper.html(`<p class="text-muted">${__("Save the AMC first.")}</p>`);
			return;
		}
		frappe.xcall("amc_tracker.cycle.get_cycle_overview", { amc: frm.doc.name }).then((data) => {
			frm.__cycle = data;
			const esc = amc_tracker.esc;
			let html = "";
			if (!data.visits.length) {
				html = `<div class="text-muted" style="padding:10px 0">${__("No engineers assigned for cycle {0} yet.", [esc(data.cycle_label)])}</div>`;
			} else {
				const rows = data.visits
					.map((v) => {
						const report = v.report
							? `<a href="${esc(v.report)}" target="_blank">${__("Report")}</a>`
							: v.included_in_combined
								? `<span class="text-muted">${__("In combined report")}</span>`
								: "-";
						const time = v.start_time ? ` ${esc(v.start_time.slice(0, 5))}${v.end_time ? "-" + esc(v.end_time.slice(0, 5)) : ""}` : "";
						return `<tr>
							<td><a href="/desk/pm-visit/${encodeURIComponent(v.name)}">${esc(v.engineer_name || v.engineer)}</a></td>
							<td>${v.expertise.map(esc).join(", ") || "-"}</td>
							<td>${esc(__(v.visit_mode || ""))}</td>
							<td>${v.visit_date ? esc(frappe.datetime.str_to_user(v.visit_date)) + time : `<span class="text-muted">${__("Not set")}</span>`}</td>
							<td>${amc_tracker.pill(v.status)}</td>
							<td>${report}</td>
						</tr>`;
					})
					.join("");
				html = `<table class="table table-bordered table-sm" style="font-size:13px;margin-bottom:8px">
					<thead><tr><th>${__("Engineer")}</th><th>${__("Expertise")}</th><th>${__("Mode")}</th>
					<th>${__("Visit Date")}</th><th>${__("Status")}</th><th>${__("Report")}</th></tr></thead>
					<tbody>${rows}</tbody></table>`;
			}
			const buttons = [];
			if (data.can_assign && frm.doc.status === "Active") {
				buttons.push(`<button class="btn btn-sm btn-primary amc-assign">${__("Assign Engineers")}</button>`);
				if (data.visits.length) buttons.push(`<button class="btn btn-sm btn-default amc-add-visit">${__("Add Visit")}</button>`);
			}
			if (data.can_sign_off) buttons.push(`<button class="btn btn-sm btn-success amc-sign-off">${__("Sign Off Cycle")}</button>`);
			field.$wrapper.html(
				`<div class="small text-muted" style="margin-bottom:6px">${__("Cycle {0} - PM due {1}", [esc(data.cycle_label), esc(frappe.datetime.str_to_user(data.due_date))])}</div>
				${html}<div style="display:flex;gap:8px">${buttons.join("")}</div>`
			);
			field.$wrapper.find(".amc-assign").on("click", () => amc_form.assign_dialog(frm));
			field.$wrapper.find(".amc-add-visit").on("click", () => frappe.new_doc("PM Visit", { amc: frm.doc.name }));
			field.$wrapper.find(".amc-sign-off").on("click", () => amc_form.sign_off(frm));
		});
	},

	buttons(frm) {
		if (frm.is_new()) return;
		const group = __("Actions");
		if (amc_tracker.is_helpdesk() && frm.doc.status === "Active") {
			frm.add_custom_button(__("Assign Engineers"), () => amc_form.assign_dialog(frm), group);
		}
		const team = [...new Map((frm.doc.engineers || []).map((r) => [r.engineer, r])).values()];
		const on_team = team.some((r) => r.engineer === frappe.session.user);
		if (frm.doc.status === "Active" && (on_team || (amc_tracker.is_helpdesk() && team.length))) {
			frm.add_custom_button(
				__("Transfer to Another Engineer"),
				() =>
					amc_tracker.transfer_dialog(frm.doc.name, {
						from_engineer: on_team ? frappe.session.user : null,
						team: amc_tracker.is_helpdesk() ? team : null,
						after: () =>
							on_team && !amc_tracker.is_helpdesk() ? frappe.set_route("List", "AMC") : frm.reload_doc(),
					}),
				group
			);
		}
		frm.add_custom_button(
			__("Email Client to Schedule"),
			() => amc_tracker.scheduling_email_dialog(frm.doc.name, null, () => frm.reload_doc()),
			group
		);
		frm.add_custom_button(
			__("Log Client Contact"),
			() => amc_tracker.contact_dialog(frm.doc.name, null, null, () => frm.reload_doc()),
			group
		);
		frm.add_custom_button(__("Contact History"), () => frappe.set_route("List", "Client Contact Log", { amc: frm.doc.name }), group);
		frm.add_custom_button(__("PM Visits"), () => frappe.set_route("List", "PM Visit", { amc: frm.doc.name }), group);
		frm.add_custom_button(__("PM Calendar"), () => frappe.set_route("List", "PM Visit", "Calendar", "default"), group);

		if (amc_tracker.is_manager() && frm.doc.cycle_status === "Reports submitted") {
			frm.add_custom_button(__("Sign Off Cycle"), () => amc_form.sign_off(frm)).addClass("btn-primary");
		}
		frm.add_custom_button(__("Refresh Timeline"), () => frm.reload_doc(), __("Notifications"));
		frm.add_custom_button(
			__("Notification Log"),
			() => frappe.set_route("List", "AMC Notification Log", { amc: frm.doc.name }),
			__("Notifications")
		);
	},

	assign_dialog(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the AMC first."));
			return;
		}
		const assigned = new Set(((frm.__cycle && frm.__cycle.visits) || []).filter((v) => v.status !== "Cancelled").map((v) => v.engineer));
		const team = (frm.doc.engineers || []).filter((r) => !assigned.has(r.engineer));
		const d = new frappe.ui.Dialog({
			title: __("Assign Engineers - cycle {0}", [frm.doc.cycle_label || ""]),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"One PM visit is created per engineer. An engineer listed with several areas of expertise gets one visit covering all of them. Each engineer then sets the visit date with the client."
					)}</p>`,
				},
				{
					fieldname: "rows",
					fieldtype: "Table",
					label: __("Engineers"),
					cannot_add_rows: false,
					in_place_edit: true,
					data: team.map((r) => ({ engineer: r.engineer, expertise: r.expertise, visit_mode: "On-site" })),
					fields: [
						{ fieldname: "engineer", fieldtype: "Link", options: "Engineer", label: __("Engineer"), in_list_view: 1, reqd: 1, columns: 4, get_query: amc_tracker.engineer_query },
						{ fieldname: "expertise", fieldtype: "Link", options: "Expertise", label: __("Expertise"), in_list_view: 1, columns: 3 },
						{ fieldname: "visit_mode", fieldtype: "Select", options: "On-site\nRemote", label: __("Visit Mode"), in_list_view: 1, default: "On-site", columns: 2 },
					],
				},
			],
			primary_action_label: __("Assign"),
			primary_action(values) {
				const merged = {};
				(values.rows || []).forEach((r) => {
					if (!r.engineer) return;
					merged[r.engineer] = merged[r.engineer] || { engineer: r.engineer, expertise: [], visit_mode: r.visit_mode || "On-site" };
					if (r.expertise && !merged[r.engineer].expertise.includes(r.expertise)) merged[r.engineer].expertise.push(r.expertise);
				});
				frappe
					.xcall("amc_tracker.cycle.assign_engineers", { amc: frm.doc.name, rows: Object.values(merged) })
					.then((r) => {
						d.hide();
						let msg = __("{0} PM visit(s) created.", [r.created.length]);
						if (r.skipped.length) msg += " " + __("Already assigned: {0}", [r.skipped.join(", ")]);
						frappe.show_alert({ message: msg, indicator: "green" }, 7);
						frm.reload_doc();
					});
			},
		});
		d.show();
		if (assigned.size && !team.length) {
			d.fields_dict.rows.df.data = [];
			d.fields_dict.rows.grid.refresh();
		}
	},

	sign_off(frm) {
		frappe.confirm(
			__("Sign off PM cycle {0}? The next PM due date rolls forward by {1} month(s) and a new cycle starts.", [
				frm.doc.cycle_label,
				frm.doc.interval_months,
			]),
			() =>
				frappe.xcall("amc_tracker.cycle.sign_off", { amc: frm.doc.name }).then((r) => {
					frappe.show_alert({ message: r.message, indicator: "green" }, 8);
					frm.reload_doc();
				})
		);
	},
};

frappe.ui.form.on("AMC Engineer", {
	// Picking an engineer fills their expertise: one row per area they have (delete the ones not needed)
	engineer(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.engineer) return;
		amc_tracker.expertise_of(row.engineer).then((list) => {
			frm.__expertise = frm.__expertise || {};
			frm.__expertise[row.engineer] = list;
			if (!list.length || row.expertise) return;
			const taken = new Set((frm.doc.engineers || []).filter((r) => r.engineer === row.engineer && r.expertise).map((r) => r.expertise));
			const todo = list.filter((x) => !taken.has(x));
			if (!todo.length) return;
			frappe.model.set_value(cdt, cdn, "expertise", todo[0]);
			todo.slice(1).forEach((x) => {
				const extra = frm.add_child("engineers", { engineer: row.engineer, expertise: x });
				frappe.model.set_value(extra.doctype, extra.name, "engineer_name", row.engineer_name);
			});
			frm.refresh_field("engineers");
		});
	},
});
