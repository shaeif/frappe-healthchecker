"""SSH collection with Netmiko (all Cisco platforms; PAN-OS / FortiOS CLI as an alternative to their APIs)."""

from hc_tracker.collectors.base import CollectorError, DeviceResult, DeviceSpec, Timer, is_read_only_command
from hc_tracker.collectors.parsers import PARSERS, merge_facts
from hc_tracker.collectors.platforms import get_plan

ERROR_MARKERS = ("% Invalid input", "% Incomplete command", "Unknown command", "Invalid command", "command parse error")


def collect_ssh(spec: DeviceSpec) -> DeviceResult:
	from netmiko import ConnectHandler
	from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

	plan = get_plan(spec.vendor)
	result = DeviceResult(spec.row_name, spec.hostname, spec.host, spec.vendor, "SSH (Netmiko)")
	if not spec.username or not spec.password:
		raise CollectorError("SSH needs a username and password")

	commands = list(plan["commands"]) + [(c, None) for c in spec.extra_commands if is_read_only_command(c)]
	params = {
		"device_type": plan["netmiko"],
		"host": spec.host,
		"port": spec.port or 22,
		"username": spec.username,
		"password": spec.password,
		"secret": spec.secret or "",
		"conn_timeout": spec.timeout,
		"auth_timeout": spec.timeout,
		"banner_timeout": spec.timeout,
		"fast_cli": False,
	}

	with Timer() as timer:
		try:
			with ConnectHandler(**params) as conn:
				if spec.secret and plan["netmiko"] in ("cisco_ios", "cisco_xe") and not conn.check_enable_mode():
					conn.enable()
				for command, parser in commands:
					try:
						output = conn.send_command(command, read_timeout=spec.timeout)
					except Exception as e:  # one command failing must not abort the device
						result.command_errors[command] = str(e)[:300]
						continue
					result.outputs[command] = output
					if any(marker in output for marker in ERROR_MARKERS):
						result.command_errors[command] = output.strip().splitlines()[0][:300] if output.strip() else "error"
						continue
					if parser:
						merge_facts(result.facts, PARSERS[parser](output))
		except NetmikoAuthenticationException as e:
			raise CollectorError(f"Authentication failed: {str(e).splitlines()[0][:200]}")
		except NetmikoTimeoutException as e:
			raise CollectorError(f"Connection timed out: {str(e).splitlines()[0][:200]}")
	result.duration = timer.elapsed
	return result
