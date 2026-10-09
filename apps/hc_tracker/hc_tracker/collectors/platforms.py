"""Per-vendor collection plan: Netmiko driver, read-only commands and the parser for each command."""

VENDORS = {
	"Cisco IOS-XE": {
		"netmiko": "cisco_xe",
		"default_method": "SSH (Netmiko)",
		"commands": [
			("show version", "cisco_ios_version"),
			("show inventory", "cisco_inventory"),
			("show processes cpu | include CPU utilization", "cisco_cpu"),
			("show processes memory | include Processor Pool", "cisco_ios_memory"),
			("show ip interface brief", None),
			("show logging", None),
		],
	},
	"Cisco IOS": {
		"netmiko": "cisco_ios",
		"default_method": "SSH (Netmiko)",
		"commands": [
			("show version", "cisco_ios_version"),
			("show inventory", "cisco_inventory"),
			("show processes cpu | include CPU utilization", "cisco_cpu"),
			("show processes memory | include Processor Pool", "cisco_ios_memory"),
			("show ip interface brief", None),
			("show logging", None),
		],
	},
	"Cisco NX-OS": {
		"netmiko": "cisco_nxos",
		"default_method": "SSH (Netmiko)",
		"commands": [
			("show version", "nxos_version"),
			("show inventory", "cisco_inventory"),
			("show system resources", "nxos_resources"),
			("show interface brief", None),
			("show logging last 200", None),
		],
	},
	"Cisco AireOS WLC": {
		"netmiko": "cisco_wlc_ssh",
		"default_method": "SSH (Netmiko)",
		"commands": [
			("show sysinfo", "aireos_sysinfo"),
			("show inventory", "cisco_inventory"),
			("show cpu", "cisco_cpu"),
			("show ap summary", "cisco_ap_summary"),
			("show client summary", None),
		],
	},
	"Cisco Catalyst 9800 WLC": {
		"netmiko": "cisco_xe",
		"default_method": "SSH (Netmiko)",
		"commands": [
			("show version", "cisco_ios_version"),
			("show inventory", "cisco_inventory"),
			("show processes cpu | include CPU utilization", "cisco_cpu"),
			("show processes memory | include Processor Pool", "cisco_ios_memory"),
			("show ap summary", "cisco_ap_summary"),
			("show wireless client summary", None),
		],
	},
	"Palo Alto PAN-OS": {
		"netmiko": "paloalto_panos",
		"default_method": "REST API",
		"commands": [
			("show system info", "panos_system_info"),
			("show system resources", "linux_top"),
			("show high-availability state", "panos_ha_state"),
			("request license info", "panos_licenses_text"),
		],
	},
	"FortiGate FortiOS": {
		"netmiko": "fortinet",
		"default_method": "REST API",
		"commands": [
			("get system status", "fortios_status"),
			("get system performance status", "fortios_performance"),
			("get system ha status", "fortios_ha_status"),
		],
	},
}


def get_plan(vendor: str) -> dict:
	plan = VENDORS.get(vendor)
	if not plan:
		raise ValueError(f"Unsupported vendor/platform: {vendor}")
	return plan
