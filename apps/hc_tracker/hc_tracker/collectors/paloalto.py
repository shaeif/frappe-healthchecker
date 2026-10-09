"""Palo Alto PAN-OS XML API collector (https://<host>/api/)."""

import xml.etree.ElementTree as ET

from hc_tracker.collectors.base import CollectorError, DeviceResult, DeviceSpec, Timer
from hc_tracker.collectors.parsers import _parse_expiry, linux_top, merge_facts, parse_uptime_days

OP_COMMANDS = {
	"show system info": "<show><system><info></info></system></show>",
	"show system resources": "<show><system><resources></resources></system></show>",
	"show high-availability state": "<show><high-availability><state></state></high-availability></show>",
	"request license info": "<request><license><info></info></license></request>",
}


def _text(node, path) -> str | None:
	found = node.find(path) if node is not None else None
	return found.text.strip() if found is not None and found.text else None


def _call(session, base_url, params, spec) -> ET.Element:
	response = session.get(base_url, params=params, verify=spec.verify_ssl, timeout=spec.timeout)
	if response.status_code >= 400:
		raise CollectorError(f"PAN-OS API HTTP {response.status_code}")
	root = ET.fromstring(response.text)
	if root.get("status") != "success":
		message = " ".join(t.strip() for t in root.itertext() if t.strip())[:300]
		raise CollectorError(f"PAN-OS API error: {message or 'unknown'}")
	return root


def collect_panos_api(spec: DeviceSpec) -> DeviceResult:
	import requests
	import urllib3

	if not spec.verify_ssl:
		urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

	result = DeviceResult(spec.row_name, spec.hostname, spec.host, spec.vendor, "REST API")
	base_url = f"https://{spec.host}:{spec.port or 443}/api/"
	session = requests.Session()

	with Timer() as timer:
		try:
			key = spec.api_key
			if not key:
				if not (spec.username and spec.password):
					raise CollectorError("PAN-OS API needs an API key, or a username and password")
				keygen = _call(
					session, base_url, {"type": "keygen", "user": spec.username, "password": spec.password}, spec
				)
				key = _text(keygen, "./result/key")
				if not key:
					raise CollectorError("PAN-OS keygen returned no key")

			for name, cmd in OP_COMMANDS.items():
				try:
					root = _call(session, base_url, {"type": "op", "cmd": cmd, "key": key}, spec)
				except CollectorError as e:
					result.command_errors[name] = str(e)
					continue
				result.outputs[name] = ET.tostring(root, encoding="unicode")
				merge_facts(result.facts, _parse(name, root))
		except requests.exceptions.SSLError as e:
			raise CollectorError(f"TLS error (untick Verify SSL for self-signed certificates): {str(e)[:200]}")
		except requests.exceptions.RequestException as e:
			raise CollectorError(f"PAN-OS API unreachable: {str(e)[:200]}")
	result.duration = timer.elapsed
	return result


def _parse(name: str, root: ET.Element) -> dict:
	res = root.find("./result")
	if name == "show system info":
		system = res.find("./system") if res is not None else None
		facts = {
			"hostname": _text(system, "hostname"),
			"model": _text(system, "model"),
			"serial_number": _text(system, "serial"),
			"software_version": _text(system, "sw-version"),
			"uptime_text": _text(system, "uptime"),
		}
		facts["uptime_days"] = parse_uptime_days(facts["uptime_text"])
		return facts
	if name == "show system resources":
		return linux_top(res.text if res is not None and res.text else "")
	if name == "show high-availability state":
		if (_text(res, "enabled") or "no").lower() != "yes":
			return {"ha_mode": "Standalone"}
		facts = {
			"ha_mode": _text(res, "group/mode") or "HA",
			"ha_state": _text(res, "group/local-info/state"),
		}
		sync = _text(res, "group/running-sync")
		if sync:
			facts["ha_in_sync"] = sync.lower() == "synchronized"
		return facts
	if name == "request license info":
		licenses = []
		for entry in res.findall(".//entry") if res is not None else []:
			licenses.append(
				{
					"name": _text(entry, "feature") or _text(entry, "description") or "license",
					"expires": _parse_expiry(_text(entry, "expires")),
					"expired": (_text(entry, "expired") or "no").lower() == "yes",
				}
			)
		return {"licenses": licenses}
	return {}
