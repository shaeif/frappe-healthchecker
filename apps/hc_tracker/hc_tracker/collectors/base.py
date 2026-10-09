"""Plain data structures shared by the collectors (no Frappe imports, safe to use in threads)."""

import time
from dataclasses import dataclass, field
from typing import Any

# Commands an engineer may add per device ("Extra Commands"): read-only verbs only.
READ_ONLY_PREFIXES = ("show ", "get ", "display ", "diagnose sys ", "diagnose hardware ")


class CollectorError(Exception):
	"""A device could not be collected (connection, authentication, API error...)."""


@dataclass
class DeviceSpec:
	"""Everything a collector needs; built in the main thread (passwords already decrypted)."""

	row_name: str
	hostname: str
	host: str
	vendor: str
	method: str = "SSH (Netmiko)"
	port: int | None = None
	username: str | None = None
	password: str | None = None
	secret: str | None = None
	api_key: str | None = None
	verify_ssl: bool = False
	timeout: int = 60
	extra_commands: list[str] = field(default_factory=list)


@dataclass
class DeviceResult:
	row_name: str
	hostname: str
	host: str
	vendor: str
	method: str
	status: str = "Failed"  # Success / Partial / Failed
	facts: dict[str, Any] = field(default_factory=dict)
	outputs: dict[str, str] = field(default_factory=dict)
	command_errors: dict[str, str] = field(default_factory=dict)
	error: str | None = None
	duration: float = 0.0


def is_read_only_command(command: str) -> bool:
	return command.strip().lower().startswith(READ_ONLY_PREFIXES)


def clean_extra_commands(text: str | None) -> list[str]:
	return [line.strip() for line in (text or "").splitlines() if line.strip()]


class Timer:
	def __enter__(self):
		self.start = time.monotonic()
		return self

	def __exit__(self, *exc):
		self.elapsed = round(time.monotonic() - self.start, 2)
		return False
