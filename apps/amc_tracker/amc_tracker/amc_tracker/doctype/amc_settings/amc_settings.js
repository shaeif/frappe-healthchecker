// Copyright (c) 2026, AMC Tracker Maintainers and contributors
// For license information, please see license.txt

const AMC_SETUP_TILES = [
	{ label: "Notification Rules", doctype: "AMC Notification Flow", icon: "bell-ring", help: "Who is notified, when and how" },
	{ label: "Notification Log", doctype: "AMC Notification Log", icon: "mail-check", help: "Every email, Teams card and pop-up sent" },
	{ label: "Engineers", doctype: "Engineer", icon: "hard-hat", help: "Engineer profiles and their expertise" },
	{ label: "Engineer Leave", doctype: "Engineer Leave", icon: "plane", help: "Engineer availability for visit dates" },
	{ label: "Public Holidays", doctype: "Public Holiday", icon: "calendar-x", help: "Non-working days (add Eid dates yearly)" },
	{ label: "Expertise", doctype: "Expertise", icon: "graduation-cap", help: "Areas of expertise of the engineers" },
	{ label: "Users", doctype: "User", icon: "users", help: "Give users the AMC roles" },
];

frappe.ui.form.on("AMC Settings", {
	refresh(frm) {
		amc_settings.render_setup(frm);
		if (amc_tracker.is_admin()) {
			amc_settings.test_buttons(frm);
		} else {
			frm.set_intro(__("Only the AMC Admin can change these settings and the notification rules."), "blue");
		}
	},
});

const amc_settings = {
	render_setup(frm) {
		const field = frm.get_field("setup_links");
		if (!field) return;
		const tiles = AMC_SETUP_TILES.filter((t) => frappe.model.can_read(t.doctype))
			.map(
				(t) => `<a class="amc-setup-tile" href="/desk/${frappe.router.slug(t.doctype)}">
					<span class="amc-setup-icon">${frappe.utils.icon(t.icon, "md")}</span>
					<span><b>${__(t.label)}</b><br><span class="text-muted small">${__(t.help)}</span></span></a>`
			)
			.join("");
		field.$wrapper.html(`
			<style>
				.amc-setup-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:10px; margin-bottom:6px; }
				.amc-setup-tile { display:flex; gap:10px; align-items:center; padding:12px 14px; border:1px solid var(--border-color);
					border-radius:10px; color:var(--text-color); text-decoration:none !important; background:var(--card-bg); }
				.amc-setup-tile:hover { border-color:var(--primary); box-shadow:var(--shadow-sm); }
				.amc-setup-icon { color:var(--primary); }
			</style>
			<div class="amc-setup-grid">${tiles}</div>`);
	},

	test_buttons(frm) {
		const call = (method, args) =>
			frappe.call({ method, args, freeze: true, callback: (r) => r.message && frappe.msgprint(r.message) });
		const group = __("Test");
		frm.add_custom_button(
			__("Send Test Email"),
			() =>
				frappe.prompt(
					{ fieldname: "recipient", fieldtype: "Data", options: "Email", label: __("Recipient"), reqd: 1, default: frappe.session.user_email },
					(values) => call("amc_tracker.api.tools.send_test_email", values),
					__("Send Test Email")
				),
			group
		);
		frm.add_custom_button(
			__("Send Test Teams Card"),
			() => call("amc_tracker.api.tools.send_test_teams_message", { webhook_url: frm.doc.default_teams_webhook_url }),
			group
		);
		frm.add_custom_button(
			__("Send Test Pop-up To Me"),
			() => frappe.call({ method: "amc_tracker.api.tools.send_test_popup", callback: (r) => r.message && frappe.show_alert(r.message) }),
			group
		);
		frm.add_custom_button(__("Send PM To-Do Now"), () => call("amc_tracker.notifications.pm_todo.send_todo_now"), group);
		frm.add_custom_button(
			__("Send Management Summary Now"),
			() =>
				frappe.prompt(
					[
						{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
						{ fieldname: "to_date", fieldtype: "Date", label: __("To Date"), default: frappe.datetime.add_days(frappe.datetime.get_today(), -1), reqd: 1 },
					],
					(values) => call("amc_tracker.notifications.summary.send_summary_now", values),
					__("Send Management Summary")
				),
			group
		);
		frm.add_custom_button(__("Run Daily Job Now"), () => call("amc_tracker.notifications.scheduler.enqueue_daily_run"), group);
	},
};
