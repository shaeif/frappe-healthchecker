"""FortiGate FortiOS REST API collector (https://<host>/api/v2/..., Bearer API token)."""

import json
from datetime import UTC, datetime

from hc_tracker.collectors.base import CollectorError, DeviceResult, DeviceSpec, Timer
from hc_tracker.collectors.parsers import merge_facts

ENDPOINTS = {
	"system status": "/api/v2/monitor/system/status",
	"resource usage": "/api/v2/monitor/system/resource/usage?resource=cpu&resource=mem&interval=1-min",
	"web-ui state": "/api/v2/monitor/web-ui/state",
	"ha checksums": "/api/v2/monitor/system/ha-checksums",
	"license status": "/api/v2/monitor/license/status",
}


def collect_fortios_api(spec: DeviceSpec) -> DeviceResult:
	import requests
	import urllib3

	if not spec.verify_ssl:
		urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

	if not spec.api_key:
		raise CollectorError("FortiGate REST API needs an API token in the API Key field")
	result = DeviceResult(spec.row_name, spec.hostname, spec.host, spec.vendor, "REST API")
	base = f"https://{spec.host}:{spec.port or 443}"
	headers = {"Authorization": f"Bearer {spec.api_key}", "Accept": "application/json"}

	with Timer() as timer:
		try:
			for name, path in ENDPOINTS.items():
				response = requests.get(base + path, headers=headers, verify=spec.verify_ssl, timeout=spec.timeout)
				if response.status_code in (401, 403):
					raise CollectorError(f"FortiOS API authentication failed (HTTP {response.status_code})")
				if response.status_code >= 400:
					result.command_errors[name] = f"HTTP {response.status_code}"
					continue
				data = response.json()
				result.outputs[name] = json.dumps(data, indent=1)
				merge_facts(result.facts, _parse(name, data))
		except requests.exceptions.SSLError as e:
			raise CollectorError(f"TLS error (untick Verify SSL for self-signed certificates): {str(e)[:200]}")
		except requests.exceptions.RequestException as e:
			raise CollectorError(f"FortiOS API unreachable: {str(e)[:200]}")
	result.duration = timer.elapsed
	return result


def _parse(name: str, data: dict) -> dict:
	res = data.get("results")
	if name == "system status":
		res = res or {}
		model = res.get("model") or " ".join(filter(None, [res.get("model_name"), res.get("model_number")]))
		return {
			"hostname": res.get("hostname"),
			"model": model,
			"serial_number": data.get("serial"),
			"software_version": data.get("version"),
		}
	if name == "resource usage":
		res = res or {}
		facts = {}
		for key, fact in (("cpu", "cpu_percent"), ("mem", "memory_percent")):
			series = res.get(key) or []
			if series and series[0].get("current") is not None:
				facts[fact] = float(series[0]["current"])
		return facts
	if name == "web-ui state":
		reboot_ms = (res or {}).get("utc_last_reboot")
		if reboot_ms:
			delta = datetime.now(UTC) - datetime.fromtimestamp(reboot_ms / 1000, UTC)
			days = round(delta.total_seconds() / 86400, 2)
			return {"uptime_days": days, "uptime_text": f"{int(days)} days"}
		return {}
	if name == "ha checksums":
		members = res or []
		if len(members) <= 1:
			return {"ha_mode": "Standalone"}
		checksums = {json.dumps((m.get("checksum") or {}).get("all") or (m.get("checksum") or {}).get("global")) for m in members}
		return {"ha_mode": "HA", "ha_state": f"{len(members)} members", "ha_in_sync": len(checksums) == 1}
	if name == "license status":
		licenses = []
		for feature, info in (res or {}).items():
			if not isinstance(info, dict) or info.get("status") in (None, "no_license", "disabled"):
				continue
			expires = info.get("expires")
			iso = datetime.fromtimestamp(expires, UTC).date().isoformat() if isinstance(expires, int | float) and expires > 0 else None
			licenses.append({"name": feature, "expires": iso, "expired": info.get("status") == "expired"})
		return {"licenses": licenses}
	return {}
