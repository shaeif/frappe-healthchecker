// AMC Team: the AMC Admin adds users and puts them in groups (AMC roles). See amc_tracker/api/team.py.
frappe.pages["amc-team"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("AMC Team"), single_column: true });
	new AMCTeam(page);
};

const TEAM_API = "amc_tracker.api.team";

class AMCTeam {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.page.set_primary_action(__("Add User"), () => this.edit(null), "add");
		this.page.add_inner_button(__("Refresh"), () => this.load());
		this.search = this.page.add_field({
			fieldname: "search",
			fieldtype: "Data",
			label: __("Search"),
			change: () => this.render(),
		});
		this.group = this.page.add_field({
			fieldname: "group",
			fieldtype: "Select",
			label: __("Group"),
			change: () => this.render(),
		});
		this.$body = $('<div class="amc-team" style="padding: 8px 0"></div>').appendTo(this.page.main);
		this.load();
	}

	load() {
		return frappe.xcall(`${TEAM_API}.get_team`).then((data) => {
			this.data = data;
			this.group.df.options = [
				{ value: "", label: __("All users") },
				...data.groups.map((g) => ({ value: g.role, label: g.label })),
				{ value: "__none", label: __("Not in a group") },
			];
			this.group.refresh();
			this.render();
		});
	}

	render() {
		const esc = amc_tracker.esc;
		const q = (this.search.get_value() || "").toLowerCase();
		const group = this.group.get_value();
		const rows = this.data.members.filter((m) => {
			if (q && !`${m.full_name} ${m.user}`.toLowerCase().includes(q)) return false;
			if (group === "__none") return !m.groups.length;
			return !group || m.groups.includes(group);
		});
		const label = (role) => (this.data.groups.find((g) => g.role === role) || {}).label || role;
		const body = rows
			.map(
				(m) => `<tr data-user="${esc(m.user)}" style="cursor:pointer${m.enabled ? "" : ";opacity:.55"}">
					<td><b>${esc(m.full_name || m.user)}</b><div class="text-muted small">${esc(m.user)}</div></td>
					<td>${
						m.groups.map((g) => `<span class="indicator-pill blue" style="margin:2px">${esc(label(g))}</span>`).join("") ||
						`<span class="text-muted small">${__("Not in a group")}</span>`
					}${m.system_manager ? `<span class="indicator-pill gray" style="margin:2px">${__("System Manager")}</span>` : ""}</td>
					<td class="small">${m.expertise.map(esc).join(", ")}${
						m.engineer_status === "Inactive" ? ` <span class="text-muted">(${__("inactive")})</span>` : ""
					}</td>
					<td class="small">${esc(m.mobile_no || "")}</td>
					<td>${
						m.enabled
							? `<span class="indicator-pill green">${__("Enabled")}</span>`
							: `<span class="indicator-pill red">${__("Disabled")}</span>`
					}</td>
				</tr>`
			)
			.join("");
		this.$body.html(`
			<p class="text-muted small">${__(
				"Groups decide what each person sees and can do. Engineers also need their areas of expertise. Click a row to change it."
			)}</p>
			<table class="table table-bordered table-hover" style="background:var(--card-bg)">
				<thead><tr><th>${__("User")}</th><th>${__("Groups")}</th><th>${__("Expertise")}</th>
				<th>${__("Mobile")}</th><th>${__("Status")}</th></tr></thead>
				<tbody>${body || `<tr><td colspan="5" class="text-muted">${__("No users")}</td></tr>`}</tbody>
			</table>`);
		this.$body.find("tr[data-user]").on("click", (e) => {
			const user = $(e.currentTarget).attr("data-user");
			this.edit(this.data.members.find((m) => m.user === user));
		});
	}

	edit(member) {
		const is_new = !member;
		const groups = this.data.groups;
		const d = new frappe.ui.Dialog({
			title: is_new ? __("Add User") : member.full_name || member.user,
			fields: [
				{ fieldname: "full_name", fieldtype: "Data", label: __("Full Name"), reqd: 1, default: member && member.full_name },
				{
					fieldname: "email",
					fieldtype: "Data",
					options: "Email",
					label: __("Email (login)"),
					reqd: 1,
					default: member && member.user,
					read_only: !is_new,
				},
				{ fieldname: "mobile_no", fieldtype: "Data", options: "Phone", label: __("Mobile"), default: member && member.mobile_no },
				{ fieldtype: "Section Break", label: __("Groups") },
				{
					fieldname: "groups",
					fieldtype: "MultiCheck",
					columns: 2,
					options: groups.map((g) => ({
						label: g.label,
						value: g.role,
						checked: member ? member.groups.includes(g.role) : false,
					})),
				},
				{ fieldtype: "Section Break", fieldname: "expertise_section", label: __("Areas of expertise (engineers)") },
				{
					fieldname: "expertise",
					fieldtype: "MultiCheck",
					columns: 2,
					options: this.data.expertise.map((x) => ({
						label: __(x),
						value: x,
						checked: member ? member.expertise.includes(x) : false,
					})),
				},
				...(is_new
					? [
							{ fieldtype: "Section Break", label: __("Login") },
							{
								fieldname: "password",
								fieldtype: "Password",
								label: __("Password"),
								description: __("Leave empty to email the user a link to set their own password."),
							},
					  ]
					: []),
			],
			primary_action_label: is_new ? __("Add User") : __("Save"),
			primary_action: (values) => {
				frappe
					.xcall(`${TEAM_API}.save_member`, {
						email: values.email,
						full_name: values.full_name,
						mobile_no: values.mobile_no || "",
						groups: values.groups || [],
						expertise: values.expertise || [],
						is_new: is_new ? 1 : 0,
						password: values.password || null,
					})
					.then(() => {
						d.hide();
						frappe.show_alert({ message: is_new ? __("User added.") : __("Saved."), indicator: "green" });
						this.load();
					});
			},
		});
		const toggle_expertise = () => {
			const on = (d.get_values(true).groups || []).includes("AMC Engineer");
			d.set_df_property("expertise_section", "hidden", on ? 0 : 1);
			d.set_df_property("expertise", "hidden", on ? 0 : 1);
		};
		if (member && member.user !== this.data.me) {
			d.add_custom_action(member.enabled ? __("Disable User") : __("Enable User"), () =>
				frappe.confirm(
					member.enabled
						? __("Disable {0}? They will no longer be able to log in.", [member.full_name || member.user])
						: __("Enable {0} again?", [member.full_name || member.user]),
					() =>
						frappe.xcall(`${TEAM_API}.set_enabled`, { user: member.user, enabled: member.enabled ? 0 : 1 }).then(() => {
							d.hide();
							this.load();
						})
				)
			);
		}
		d.show();
		d.fields_dict.groups.$wrapper.on("change", "input[type=checkbox]", toggle_expertise);
		toggle_expertise();
	}
}
