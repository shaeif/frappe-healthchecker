"""Phase 2 (structure only): automated health-check data collection.

The plan:
  * Cisco IOS / IOS-XE / NX-OS switches and AireOS / Catalyst 9800 WLCs over SSH with Netmiko
  * Palo Alto PAN-OS via the XML API (api_key)
  * FortiGate FortiOS via the REST API (api_key token)
Collected output will be stored as File attachments on the contract and summarised into
findings_summary. Today this module only builds and logs the collection plan; it never connects
to a device. Add "netmiko" to pyproject.toml dependencies when implementing `_collect_ssh`.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

NETMIKO_DEVICE_TYPES = {
	"Cisco IOS-XE": "cisco_xe",
	"Cisco IOS": "cisco_ios",
	"Cisco NX-OS": "cisco_nxos",
	"Cisco AireOS WLC": "cisco_wlc_ssh",
	"Cisco Catalyst 9800 WLC": "cisco_xe",
	"Palo Alto PAN-OS": "paloalto_panos",
	"FortiGate FortiOS": "fortinet",
}

SHOW_COMMANDS = {
	"cisco_xe": ["show version", "show inventory", "show processes cpu sorted | ex 0.00", "show logging | last 200"],
	"cisco_ios": ["show version", "show inventory", "show processes cpu sorted", "show logging"],
	"cisco_nxos": ["show version", "show inventory", "show system resources", "show logging last 200"],
	"cisco_wlc_ssh": ["show sysinfo", "show ap summary", "show client summary"],
	"paloalto_panos": ["show system info", "show high-availability state", "show system resources"],
	"fortinet": ["get system status", "get system performance status", "diagnose sys ha status"],
}

REST_VENDORS = {"Palo Alto PAN-OS", "FortiGate FortiOS"}


@frappe.whitelist()
def enqueue_collection(contract: str):
	frappe.only_for(("System Manager", "HC Technical Manager"))
	frappe.get_doc("HC Contract", contract).check_permission("write")
	frappe.enqueue(
		"hc_tracker.collectors.jobs.collect_contract_data",
		queue="long",
		timeout=3600,
		contract=contract,
		job_id=f"hc_collect::{contract}",
		deduplicate=True,
	)
	return _("Collection job queued for {0} (Phase 2 stub: builds the plan only).").format(contract)


def collect_contract_data(contract: str):
	"""Background job (queue: long). Builds the per-device collection plan and records it."""
	doc = frappe.get_doc("HC Contract", contract)
	plan_lines = []
	for device in doc.get("devices") or []:
		if not cint(device.enabled):
			continue
		plan = build_device_plan(device)
		plan_lines.append(
			f"<li><b>{frappe.utils.escape_html(device.hostname)}</b> ({frappe.utils.escape_html(device.ip_address or '-')}) - "
			f"{frappe.utils.escape_html(plan['method'])}: {frappe.utils.escape_html(', '.join(plan['commands']) or '-')}</li>"
		)
		frappe.db.set_value(device.doctype, device.name, "last_collected_on", now_datetime(), update_modified=False)

	doc.add_comment(
		"Comment",
		_("<p><b>Phase 2 collection stub</b> - no device was contacted. Planned collection:</p><ul>{0}</ul>").format(
			"".join(plan_lines) or "<li>-</li>"
		),
	)
	frappe.db.commit()


def build_device_plan(device) -> dict:
	"""Return what would be collected for a device. Credentials are read only when actually used."""
	device_type = NETMIKO_DEVICE_TYPES.get(device.vendor or "", "autodetect")
	if device.connection_method == "REST API" or (device.vendor in REST_VENDORS and device.connection_method != "SSH (Netmiko)"):
		return {"method": "REST API", "commands": ["system status", "HA status", "resource usage"]}
	return {"method": f"SSH via Netmiko ({device_type})", "commands": SHOW_COMMANDS.get(device_type, ["show version"])}


def _collect_ssh(device) -> dict:  # pragma: no cover - Phase 2
	"""Placeholder for the real Netmiko collector (Phase 2)."""
	raise NotImplementedError(
		"Phase 2: install netmiko and implement ConnectHandler(device_type=..., host=device.ip_address, "
		"username=device.username, password=device.get_password('password'), "
		"secret=device.get_password('enable_secret', raise_exception=False))"
	)
