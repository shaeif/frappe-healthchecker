"""Link-field search queries."""

import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def users_with_role(doctype, txt, searchfield, start, page_len, filters):
	"""Enabled system users holding `filters["role"]` (used by the user fields of AMC, PM Visit and Engineer Leave)."""
	role = (filters or {}).get("role")
	if not role:
		return []
	return frappe.db.sql(
		"""
		select distinct u.name, u.full_name
		from `tabUser` u
		inner join `tabHas Role` hr on hr.parent = u.name and hr.parenttype = 'User'
		where hr.role = %(role)s
			and u.enabled = 1
			and u.name not in ('Administrator', 'Guest')
			and (u.name like %(txt)s or u.full_name like %(txt)s)
		order by u.full_name, u.name
		limit %(page_len)s offset %(start)s
		""",
		{"role": role, "txt": f"%{txt}%", "start": int(start or 0), "page_len": int(page_len or 20)},
	)
