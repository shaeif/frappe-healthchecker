"""Collect many devices in parallel. Thread-safe: no Frappe/database access in here."""

import traceback
from concurrent.futures import ThreadPoolExecutor

from hc_tracker.collectors.base import CollectorError, DeviceResult, DeviceSpec
from hc_tracker.collectors.platforms import get_plan


def collect_device(spec: DeviceSpec) -> DeviceResult:
	method = spec.method or get_plan(spec.vendor)["default_method"]
	try:
		if method == "REST API" and spec.vendor == "Palo Alto PAN-OS":
			from hc_tracker.collectors.paloalto import collect_panos_api

			result = collect_panos_api(spec)
		elif method == "REST API" and spec.vendor == "FortiGate FortiOS":
			from hc_tracker.collectors.fortinet import collect_fortios_api

			result = collect_fortios_api(spec)
		elif method == "REST API":
			raise CollectorError(f"REST API collection is not available for {spec.vendor}; use SSH (Netmiko)")
		else:
			from hc_tracker.collectors.ssh import collect_ssh

			result = collect_ssh(spec)
	except CollectorError as e:
		return DeviceResult(spec.row_name, spec.hostname, spec.host, spec.vendor, method, status="Failed", error=str(e))
	except Exception as e:
		detail = traceback.format_exc(limit=3)
		return DeviceResult(
			spec.row_name, spec.hostname, spec.host, spec.vendor, method, status="Failed",
			error=f"{type(e).__name__}: {str(e)[:300]}\n{detail[-800:]}",
		)

	core = ("software_version", "cpu_percent", "memory_percent", "uptime_days")
	result.status = "Success" if any(result.facts.get(k) is not None for k in core) and not result.command_errors else (
		"Partial" if result.outputs else "Failed"
	)
	if result.status == "Failed" and not result.error:
		result.error = "No output collected"
	return result


def collect_all(specs: list[DeviceSpec], parallelism: int = 4, progress=None) -> list[DeviceResult]:
	"""Run collect_device for every spec in a thread pool. `progress(done, total, result)` is called
	from the calling thread (results are consumed in order), so it may use Frappe APIs."""
	results: list[DeviceResult] = []
	total = len(specs)
	with ThreadPoolExecutor(max_workers=max(1, min(parallelism, total or 1))) as pool:
		for done, result in enumerate(pool.map(collect_device, specs), start=1):
			results.append(result)
			if progress:
				progress(done, total, result)
	return results
