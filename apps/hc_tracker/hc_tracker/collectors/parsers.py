"""Tolerant text parsers for device output. Each returns a dict of facts; missing data is simply absent.

Fact keys: hostname, software_version, model, serial_number, uptime_text, uptime_days, cpu_percent,
memory_percent, ha_mode, ha_state, ha_in_sync (True/False), ap_count, licenses (list of
{"name", "expires" (ISO date or None), "expired" (bool)}).
"""

import re
from datetime import date, datetime


def _num(value) -> float | None:
	try:
		return float(str(value).replace(",", "").strip())
	except (TypeError, ValueError):
		return None


def _pct(used, total) -> float | None:
	used, total = _num(used), _num(total)
	if not used or not total:
		return None
	return round(used * 100.0 / total, 1)


def parse_uptime_days(text: str | None) -> float | None:
	"""'1 year, 2 weeks, 3 days, 4 hours', '120 day(s), 3 hour(s)', '120 days, 3:04:05',
	'120 days 3 hrs 4 mins' -> days (float)."""
	if not text:
		return None
	t = text.lower()
	units = {"year": 365, "week": 7, "day": 1, "hour": 1 / 24, "hr": 1 / 24, "minute": 1 / 1440, "min": 1 / 1440}
	total, found = 0.0, False
	for unit, factor in units.items():
		for m in re.finditer(rf"(\d+)\s*{unit}s?(?:\(s\))?(?![a-z])", t):
			total += int(m.group(1)) * factor
			found = True
		t = re.sub(rf"(\d+)\s*{unit}s?(?:\(s\))?(?![a-z])", " ", t)
	hms = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", t)
	if hms:
		total += int(hms.group(1)) / 24 + int(hms.group(2)) / 1440
		found = True
	return round(total, 2) if found else None


def _first(pattern: str, text: str, flags=re.IGNORECASE | re.MULTILINE) -> str | None:
	m = re.search(pattern, text or "", flags)
	return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Cisco IOS / IOS-XE / C9800
# ---------------------------------------------------------------------------


def cisco_ios_version(text: str) -> dict:
	facts = {}
	version = _first(r"Cisco IOS[ -]XE Software,? Version\s+([\w.()\-]+)", text) or _first(
		r"Cisco IOS Software.*?Version\s+([\w.()\-]+)", text
	)
	if version:
		facts["software_version"] = version.rstrip(",")
	m = re.search(r"^(\S+) uptime is (.+)$", text or "", re.MULTILINE)
	if m:
		facts["hostname"] = m.group(1)
		facts["uptime_text"] = m.group(2).strip()
		facts["uptime_days"] = parse_uptime_days(m.group(2))
	model = _first(r"^Model Number\s*:\s*(\S+)", text) or _first(r"^cisco (\S+) \(.*?\) processor", text)
	if model:
		facts["model"] = model
	serial = _first(r"^System Serial Number\s*:\s*(\S+)", text) or _first(r"Processor board ID (\S+)", text)
	if serial:
		facts["serial_number"] = serial
	return facts


def cisco_inventory(text: str) -> dict:
	m = re.search(r"PID:\s*([^\s,]+)\s*,.*?SN:\s*(\S+)", text or "", re.IGNORECASE)
	return {"model": m.group(1), "serial_number": m.group(2)} if m else {}


def cisco_cpu(text: str) -> dict:
	five_min = _first(r"five minutes:\s*(\d+)%", text)
	if five_min is not None:
		return {"cpu_percent": float(five_min)}
	load = _first(r"Current CPU\(s\) load:\s*(\d+)%", text)  # AireOS "show cpu"
	return {"cpu_percent": float(load)} if load is not None else {}


def cisco_ios_memory(text: str) -> dict:
	m = re.search(r"Processor Pool Total:\s*(\d+)\s+Used:\s*(\d+)", text or "", re.IGNORECASE)
	return {"memory_percent": _pct(m.group(2), m.group(1))} if m else {}


def cisco_ap_summary(text: str) -> dict:
	count = _first(r"Number of APs\.*:?\s*(\d+)", text)
	return {"ap_count": int(count)} if count is not None else {}


# ---------------------------------------------------------------------------
# Cisco NX-OS
# ---------------------------------------------------------------------------


def nxos_version(text: str) -> dict:
	facts = {}
	version = _first(r"NXOS:\s*version\s+(\S+)", text) or _first(r"system:\s+version\s+(\S+)", text)
	if version:
		facts["software_version"] = version
	uptime = _first(r"Kernel uptime is (.+)$", text)
	if uptime:
		facts["uptime_text"] = uptime
		facts["uptime_days"] = parse_uptime_days(uptime)
	model = _first(r"^\s*cisco (Nexus\S*\s+\S+)\s+[Cc]hassis", text)
	if model:
		facts["model"] = model
	serial = _first(r"Processor Board ID\s+(\S+)", text)
	if serial:
		facts["serial_number"] = serial
	hostname = _first(r"Device name:\s*(\S+)", text)
	if hostname:
		facts["hostname"] = hostname
	return facts


def nxos_resources(text: str) -> dict:
	facts = {}
	idle = _first(r"CPU states\s*:.*?([\d.]+)%\s*idle", text)
	if idle is not None:
		facts["cpu_percent"] = round(100 - float(idle), 1)
	m = re.search(r"Memory usage:\s*(\d+)K total,\s*(\d+)K used", text or "", re.IGNORECASE)
	if m:
		facts["memory_percent"] = _pct(m.group(2), m.group(1))
	return facts


# ---------------------------------------------------------------------------
# Cisco AireOS WLC
# ---------------------------------------------------------------------------


def aireos_sysinfo(text: str) -> dict:
	facts = {}
	version = _first(r"Product Version\.*\s*(\S+)", text)
	if version:
		facts["software_version"] = version
	uptime = _first(r"System Up Time\.*\s*(.+)$", text)
	if uptime:
		facts["uptime_text"] = uptime
		facts["uptime_days"] = parse_uptime_days(uptime)
	name = _first(r"System Name\.*\s*(\S+)", text)
	if name:
		facts["hostname"] = name
	return facts


# ---------------------------------------------------------------------------
# Palo Alto PAN-OS (SSH text output)
# ---------------------------------------------------------------------------


def panos_system_info(text: str) -> dict:
	facts = {}
	for key, fact in (
		("sw-version", "software_version"),
		("model", "model"),
		("serial", "serial_number"),
		("hostname", "hostname"),
		("uptime", "uptime_text"),
	):
		value = _first(rf"^\s*{re.escape(key)}:\s*(.+)$", text)
		if value:
			facts[fact] = value
	if facts.get("uptime_text"):
		facts["uptime_days"] = parse_uptime_days(facts["uptime_text"])
	return facts


def linux_top(text: str) -> dict:
	"""PAN-OS 'show system resources' (top). CPU from the idle column, memory from Mem: line."""
	facts = {}
	idle = _first(r"%Cpu\(s\):.*?([\d.]+)\s*id", text)
	if idle is not None:
		facts["cpu_percent"] = round(100 - float(idle), 1)
	m = re.search(r"(?:MiB|KiB)\s+Mem\s*:\s*([\d.]+)\s+total,\s*([\d.]+)\s+free,\s*([\d.]+)\s+used", text or "")
	if m:
		facts["memory_percent"] = _pct(m.group(3), m.group(1))
	return facts


def panos_ha_state(text: str) -> dict:
	if re.search(r"HA not enabled|enabled:\s*no", text or "", re.IGNORECASE):
		return {"ha_mode": "Standalone"}
	facts = {}
	mode = _first(r"^\s*Mode:\s*(.+)$", text)
	state = _first(r"Local Information:.*?State:\s*(\S+)", text, re.IGNORECASE | re.DOTALL) or _first(
		r"^\s*State:\s*(\S+)", text
	)
	if mode:
		facts["ha_mode"] = mode
	if state:
		facts["ha_state"] = state
	sync = _first(r"(?:Running Configuration|Config sync).*?:\s*(synchronized|not synchronized|\S+)", text)
	if sync:
		facts["ha_in_sync"] = sync.lower() == "synchronized"
	return facts


def _parse_expiry(value: str | None) -> str | None:
	if not value or value.strip().lower() in ("never", "n/a", ""):
		return None
	value = value.strip()
	for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
		try:
			return datetime.strptime(value, fmt).date().isoformat()
		except ValueError:
			continue
	return None


def panos_licenses_text(text: str) -> dict:
	licenses = []
	for block in re.split(r"\n\s*\n", text or ""):
		feature = _first(r"Feature:\s*(.+)$", block)
		if not feature:
			continue
		expires = _first(r"Expires:\s*(.+)$", block)
		expired = (_first(r"Expired\??:\s*(\S+)", block) or "no").lower() == "yes"
		licenses.append({"name": feature, "expires": _parse_expiry(expires), "expired": expired})
	return {"licenses": licenses} if licenses else {}


# ---------------------------------------------------------------------------
# FortiGate FortiOS (SSH text output)
# ---------------------------------------------------------------------------


def fortios_status(text: str) -> dict:
	facts = {}
	m = re.search(r"^Version:\s*(\S+)\s+(v[\d.]+)", text or "", re.MULTILINE)
	if m:
		facts["model"] = m.group(1)
		facts["software_version"] = m.group(2)
	serial = _first(r"^Serial-Number:\s*(\S+)", text)
	if serial:
		facts["serial_number"] = serial
	hostname = _first(r"^Hostname:\s*(\S+)", text)
	if hostname:
		facts["hostname"] = hostname
	ha = _first(r"^Current HA mode:\s*(.+)$", text)
	if ha:
		facts["ha_mode"] = ha
	return facts


def fortios_performance(text: str) -> dict:
	facts = {}
	idle = _first(r"^CPU states:.*?(\d+)%\s*idle", text)
	if idle is not None:
		facts["cpu_percent"] = float(100 - int(idle))
	mem = _first(r"^Memory:.*?\(([\d.]+)%\)", text)
	if mem is not None:
		facts["memory_percent"] = float(mem)
	uptime = _first(r"^Uptime:\s*(.+)$", text)
	if uptime:
		facts["uptime_text"] = re.sub(r"\s+", " ", uptime)
		facts["uptime_days"] = parse_uptime_days(uptime)
	return facts


def fortios_ha_status(text: str) -> dict:
	facts = {}
	mode = _first(r"^HA Health Status:\s*(.+)$", text)
	if mode:
		facts["ha_state"] = mode
	if re.search(r"out-of-sync", text or "", re.IGNORECASE):
		facts["ha_in_sync"] = False
	elif re.search(r"in-sync", text or "", re.IGNORECASE):
		facts["ha_in_sync"] = True
	return facts


PARSERS = {
	"cisco_ios_version": cisco_ios_version,
	"cisco_inventory": cisco_inventory,
	"cisco_cpu": cisco_cpu,
	"cisco_ios_memory": cisco_ios_memory,
	"cisco_ap_summary": cisco_ap_summary,
	"nxos_version": nxos_version,
	"nxos_resources": nxos_resources,
	"aireos_sysinfo": aireos_sysinfo,
	"panos_system_info": panos_system_info,
	"linux_top": linux_top,
	"panos_ha_state": panos_ha_state,
	"panos_licenses_text": panos_licenses_text,
	"fortios_status": fortios_status,
	"fortios_performance": fortios_performance,
	"fortios_ha_status": fortios_ha_status,
}


def merge_facts(facts: dict, new: dict):
	"""Keep the first non-empty value per key (commands are ordered by reliability)."""
	for key, value in (new or {}).items():
		if value in (None, "", []):
			continue
		if key not in facts or facts[key] in (None, "", []):
			facts[key] = value


def days_until(iso_date: str | None, today: date) -> int | None:
	if not iso_date:
		return None
	return (date.fromisoformat(iso_date) - today).days
