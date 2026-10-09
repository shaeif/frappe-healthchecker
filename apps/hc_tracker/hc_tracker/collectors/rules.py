"""Turn collected facts into health-check findings (no Frappe imports)."""

from dataclasses import asdict, dataclass
from datetime import date

from hc_tracker.collectors.base import DeviceResult
from hc_tracker.collectors.parsers import days_until

SEVERITY_ORDER = {"Critical": 0, "Warning": 1, "Info": 2}


@dataclass
class Thresholds:
	cpu: float = 80
	memory: float = 85
	uptime_days: int = 365
	license_days: int = 60


@dataclass
class Finding:
	severity: str
	device: str
	title: str
	detail: str
	recommendation: str

	def as_dict(self):
		return asdict(self)


def evaluate(results: list[DeviceResult], thresholds: Thresholds, today: date) -> list[Finding]:
	findings: list[Finding] = []
	for r in results:
		name = r.hostname or r.host
		f = r.facts

		if r.status == "Failed":
			findings.append(
				Finding("Critical", name, "Data collection failed", r.error or "Unknown error",
					"Check reachability, credentials and the connection method, then re-run the collection.")
			)
			continue
		if r.command_errors:
			findings.append(
				Finding("Info", name, f"{len(r.command_errors)} command(s) returned an error",
					"; ".join(f"{k}: {v}" for k, v in list(r.command_errors.items())[:5]),
					"Review the raw output; the platform may not support these commands.")
			)

		cpu = f.get("cpu_percent")
		if cpu is not None and cpu >= thresholds.cpu:
			findings.append(
				Finding("Critical" if cpu >= 90 else "Warning", name, f"High CPU utilisation ({cpu:.0f}%)",
					f"CPU is {cpu:.0f}% (threshold {thresholds.cpu:.0f}%).",
					"Identify the top processes/sessions and review traffic, logging and control-plane load.")
			)
		mem = f.get("memory_percent")
		if mem is not None and mem >= thresholds.memory:
			findings.append(
				Finding("Critical" if mem >= 95 else "Warning", name, f"High memory utilisation ({mem:.0f}%)",
					f"Memory is {mem:.0f}% used (threshold {thresholds.memory:.0f}%).",
					"Check for memory leaks / known bugs for this release and plan an upgrade or reload window.")
			)
		up = f.get("uptime_days")
		if up is not None and up >= thresholds.uptime_days:
			findings.append(
				Finding("Warning", name, f"Long uptime ({int(up)} days)",
					f"Device has not been reloaded for {int(up)} days ({f.get('uptime_text', '')}).",
					f"Software {f.get('software_version', '')} is likely missing security fixes; verify against the vendor's recommended release and schedule an upgrade.")
			)
		if f.get("ha_in_sync") is False:
			findings.append(
				Finding("Critical", name, "HA configuration not synchronised",
					f"HA mode {f.get('ha_mode', '')}, state {f.get('ha_state', '')}: peers are out of sync.",
					"Synchronise the HA configuration and verify failover readiness.")
			)
		for lic in f.get("licenses") or []:
			left = days_until(lic.get("expires"), today)
			if lic.get("expired") or (left is not None and left < 0):
				findings.append(
					Finding("Critical", name, f"License expired: {lic['name']}",
						f"Expired on {lic.get('expires') or 'unknown date'}.",
						"Renew the subscription; security services stop updating when expired.")
				)
			elif left is not None and left <= thresholds.license_days:
				findings.append(
					Finding("Warning", name, f"License expiring in {left} days: {lic['name']}",
						f"Expires on {lic['expires']}.", "Raise the renewal with the account manager.")
				)
		if f.get("ap_count") is not None:
			findings.append(
				Finding("Info", name, f"{f['ap_count']} access points joined", "Wireless controller AP count.",
					"Compare with the expected AP inventory.")
			)

	versions = sorted({(r.vendor, r.facts.get("software_version")) for r in results if r.facts.get("software_version")})
	if versions:
		findings.append(
			Finding("Info", "All devices", "Software versions in use",
				", ".join(f"{v} {ver}" for v, ver in versions),
				"Check each release against the vendor's recommended / end-of-life notices.")
		)
	findings.sort(key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.device))
	return findings


def findings_text(findings: list[Finding]) -> str:
	lines = []
	for x in findings:
		if x.severity == "Info" and x.device == "All devices":
			continue
		lines.append(f"[{x.severity}] {x.device}: {x.title}")
	return "\n".join(lines) if lines else "No issues found by the automated checks."
