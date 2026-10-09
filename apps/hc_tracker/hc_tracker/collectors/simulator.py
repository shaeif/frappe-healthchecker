"""HC lab device simulator - fake network devices for testing Phase 2 without real hardware.

Starts (all on one host, see docker-compose.lab.yml):
  SSH 2201  SW-CORE-01   Cisco IOS-XE C9300   (high CPU 85%  -> Warning, uptime > 1 year -> Warning)
  SSH 2202  N9K-CORE     Cisco NX-OS          (uptime 412 days -> Warning)
  SSH 2203  WLC-01       Cisco AireOS WLC     (30 APs; WLC "User:/Password:" login)
  SSH 2204  WLC-9800     Catalyst 9800 WLC    (healthy, 120 APs)
  HTTPS 8443  PA-DOHA-01  Palo Alto XML API   (uptime 520 days, expired + expiring licenses)
  HTTPS 9443  FGT-DOHA-01 FortiGate REST API  (memory 91%, HA out of sync, license expiring)

Credentials come from the environment (no defaults):
  LAB_DEVICE_USERNAME (default "hcadmin"), LAB_DEVICE_PASSWORD (required), LAB_DEVICE_API_KEY (required)

Run:  python -m hc_tracker.collectors.simulator
"""

import datetime as dt
import json
import os
import socket
import ssl
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import paramiko

USERNAME = os.environ.get("LAB_DEVICE_USERNAME", "hcadmin")
PASSWORD = os.environ.get("LAB_DEVICE_PASSWORD")
API_KEY = os.environ.get("LAB_DEVICE_API_KEY")


def _today():
	return dt.date.today()


def _pan_date(days):
	return (_today() + dt.timedelta(days=days)).strftime("%B %d, %Y")


def _epoch(days):
	return int(dt.datetime.combine(_today() + dt.timedelta(days=days), dt.time()).timestamp())


# ---------------------------------------------------------------------------
# Device profiles (realistic CLI output)
# ---------------------------------------------------------------------------

IOSXE_SW = {
	"prompt": "SW-CORE-01#",
	"commands": {
		"show version": """Cisco IOS XE Software, Version 17.09.04a
Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a, RELEASE SOFTWARE (fc3)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2023 by Cisco Systems, Inc.

ROM: IOS-XE ROMMON
BOOTLDR: System Bootstrap, Version 17.9.1r, RELEASE SOFTWARE (P)

SW-CORE-01 uptime is 1 year, 6 weeks, 2 days, 3 hours, 12 minutes
Uptime for this control processor is 1 year, 6 weeks, 2 days, 3 hours, 14 minutes
System returned to ROM by Reload Command
System image file is "flash:packages.conf"

cisco C9300-48P (X86) processor with 1331521K/6147K bytes of memory.
Processor board ID FOC2233X0AB
48 Gigabit Ethernet interfaces
8 Ten Gigabit Ethernet interfaces

Model Number                       : C9300-48P
System Serial Number               : FOC2233X0AB
""",
		"show inventory": """NAME: "c93xx Stack", DESCR: "c93xx Stack"
PID: C9300-48P         , VID: V02  , SN: FOC2233X0AB

NAME: "Switch 1", DESCR: "C9300-48P"
PID: C9300-48P         , VID: V02  , SN: FOC2233X0AB
""",
		"show processes cpu | include CPU utilization": "CPU utilization for five seconds: 88%/2%; one minute: 86%; five minutes: 85%",
		"show processes memory | include Processor Pool": "Processor Pool Total: 1331521536 Used:  612399872 Free:  719121664",
		"show ip interface brief": """Interface              IP-Address      OK? Method Status                Protocol
Vlan1                  unassigned      YES NVRAM  administratively down down
Vlan10                 10.10.10.1      YES NVRAM  up                    up
GigabitEthernet1/0/1   unassigned      YES unset  up                    up
GigabitEthernet1/0/2   unassigned      YES unset  down                  down
""",
		"show logging": """Syslog logging: enabled (0 messages dropped, 3 messages rate-limited)
*Oct  8 07:12:01.123: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/2, changed state to down
*Oct  8 07:12:02.123: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/2, changed state to down
""",
	},
}

NXOS = {
	"prompt": "N9K-CORE#",
	"commands": {
		"show version": """Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Copyright (C) 2002-2022, Cisco and/or its affiliates.

Software
  BIOS: version 07.69
 NXOS: version 9.3(10)
  BIOS compile time:  04/08/2021
  NXOS image file is: bootflash:///nxos.9.3.10.bin

Hardware
  cisco Nexus9000 C93180YC-EX chassis
  Intel(R) Xeon(R) CPU  @ 1.80GHz with 24538612 kB of memory.
  Processor Board ID FDO21120U8N

  Device name: N9K-CORE
  bootflash:   53298520 kB
Kernel uptime is 412 day(s), 5 hour(s), 33 minute(s), 9 second(s)
""",
		"show inventory": """NAME: "Chassis",  DESCR: "Nexus9000 C93180YC-EX chassis"
PID: N9K-C93180YC-EX     ,  VID: V03 ,  SN: FDO21120U8N
""",
		"show system resources": """Load average:   1 minute: 0.42   5 minutes: 0.38   15 minutes: 0.40
Processes:   601 total, 1 running
CPU states  :   3.20% user,   2.55% kernel,   94.25% idle
Memory usage:   24538612K total,   9561728K used,   14976884K free
""",
		"show interface brief": "Eth1/1  1  eth  trunk  up  none  10G(D) --\nEth1/2  1  eth  trunk  up  none  10G(D) --\n",
		"show logging last 200": "2026 Oct  8 07:00:01 N9K-CORE %ETHPORT-5-IF_UP: Interface Ethernet1/1 is up\n",
	},
}

AIREOS = {
	"prompt": "(Cisco Controller) >",
	"wlc_login": True,
	"commands": {
		"show sysinfo": """Manufacturer's Name.............................. Cisco Systems Inc.
Product Name..................................... Cisco Controller
Product Version.................................. 8.10.185.0
Bootloader Version............................... 8.5.103.0
Build Type....................................... DATA + WPS

System Name...................................... WLC-01
System Location.................................. Doha DC
System Up Time................................... 45 days 3 hrs 12 mins 5 secs
""",
		"show inventory": 'NAME: "Chassis"   , DESCR: "Cisco 5520 Wireless Controller"\nPID: AIR-CT5520-K9,  VID: V01,  SN: FCH2125V0AB\n',
		"show cpu": "Current CPU(s) load: 12%\n\nIndividual CPU load: 10%/0%, 14%/0%\n",
		"show ap summary": """Number of APs.................................... 30

Global AP User Name.............................. admin
AP Name             Slots  AP Model              Ethernet MAC       Location          Country  IP Address       Clients
------------------  -----  --------------------  -----------------  ----------------  -------  ---------------  -------
AP-FLOOR1-01         2     AIR-AP2802I-E-K9      70:db:98:00:00:01  Floor 1           QA       10.20.0.11       12
""",
		"show client summary": "Number of Clients................................ 245\n",
	},
}

C9800 = {
	"prompt": "WLC-9800#",
	"commands": {
		"show version": """Cisco IOS XE Software, Version 17.12.03
Cisco IOS Software [Dublin], C9800 Software (C9800_IOSXE-K9), Version 17.12.3, RELEASE SOFTWARE (fc7)

WLC-9800 uptime is 12 weeks, 1 day, 5 hours, 2 minutes

cisco C9800-40-K9 (KATAR) processor (revision KATAR) with 7884148K/6147K bytes of memory.
Processor board ID TTM241200AB

Model Number                       : C9800-40-K9
System Serial Number               : TTM241200AB
""",
		"show inventory": 'NAME: "Chassis", DESCR: "Cisco C9800-40 Chassis"\nPID: C9800-40-K9       , VID: 01  , SN: TTM241200AB\n',
		"show processes cpu | include CPU utilization": "CPU utilization for five seconds: 15%/1%; one minute: 14%; five minutes: 15%",
		"show processes memory | include Processor Pool": "Processor Pool Total: 3000000000 Used:  1800000000 Free:  1200000000",
		"show ap summary": "Number of APs: 120\n\nAP Name   Slots  AP Model  Ethernet MAC  Radio MAC  Location  Country  IP Address  State\n",
		"show wireless client summary": "Number of Clients: 1450\n",
	},
}

SSH_DEVICES = {2201: IOSXE_SW, 2202: NXOS, 2203: AIREOS, 2204: C9800}
SESSION_COMMANDS = ("terminal", "config paging", "set cli", "no paging")


# ---------------------------------------------------------------------------
# SSH server
# ---------------------------------------------------------------------------


class _Server(paramiko.ServerInterface):
	def __init__(self):
		self.event = threading.Event()

	def check_auth_password(self, username, password):
		return paramiko.AUTH_SUCCESSFUL if (username == USERNAME and password == PASSWORD) else paramiko.AUTH_FAILED

	def get_allowed_auths(self, username):
		return "password"

	def check_channel_request(self, kind, chanid):
		return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

	def check_channel_pty_request(self, *args):
		return True

	def check_channel_shell_request(self, channel):
		self.event.set()
		return True


def _readline(chan, echo=True) -> str | None:
	buf = ""
	while True:
		data = chan.recv(1024)
		if not data:
			return None
		for ch in data.decode(errors="ignore"):
			if ch in "\r\n":
				if echo:
					chan.send("\r\n")
				return buf
			buf += ch
			if echo:
				chan.send(ch)


def _session(chan, profile):
	prompt = profile["prompt"]
	try:
		if profile.get("wlc_login"):
			chan.send("\r\n(Cisco Controller)\r\nUser: ")
			if _readline(chan) != USERNAME:
				chan.close()
				return
			chan.send("Password:")
			if _readline(chan, echo=False) != PASSWORD:
				chan.send("\r\nLogin incorrect\r\n")
				chan.close()
				return
		chan.send(f"\r\n{prompt}")
		while True:
			line = _readline(chan)
			if line is None:
				return
			cmd = line.strip()
			if cmd in ("exit", "logout", "quit"):
				chan.close()
				return
			if not cmd:
				output = ""
			elif cmd in profile["commands"]:
				output = profile["commands"][cmd]
			elif cmd.startswith(SESSION_COMMANDS) or cmd in ("enable",):
				output = ""
			else:
				output = "                 ^\r\n% Invalid input detected at '^' marker.\r\n"
			if output:
				chan.send(output.replace("\r\n", "\n").replace("\n", "\r\n"))
				if not output.endswith("\n"):
					chan.send("\r\n")
			chan.send(prompt)
	except (OSError, EOFError):
		pass
	finally:
		try:
			chan.close()
		except Exception:
			pass


def _serve_ssh(port, profile, host_key):
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	sock.bind(("0.0.0.0", port))
	sock.listen(50)
	while True:
		client, _addr = sock.accept()
		threading.Thread(target=_handle_ssh_client, args=(client, profile, host_key), daemon=True).start()


def _handle_ssh_client(client, profile, host_key):
	transport = paramiko.Transport(client)
	transport.add_server_key(host_key)
	server = _Server()
	try:
		transport.start_server(server=server)
		chan = transport.accept(30)
		if chan is None:
			return
		server.event.wait(10)
		_session(chan, profile)
	except Exception:
		pass
	finally:
		time.sleep(0.2)
		transport.close()


# ---------------------------------------------------------------------------
# HTTPS APIs
# ---------------------------------------------------------------------------


def _panos_response(params) -> tuple[int, str]:
	ok = lambda body: (200, f'<response status="success">{body}</response>')  # noqa: E731
	err = lambda msg: (403, f'<response status="error"><msg><line>{msg}</line></msg></response>')  # noqa: E731
	if params.get("type") == "keygen":
		if params.get("user") == USERNAME and params.get("password") == PASSWORD:
			return ok(f"<result><key>{API_KEY}</key></result>")
		return err("Invalid Credential")
	if params.get("key") != API_KEY:
		return err("Invalid API key")
	cmd = params.get("cmd", "")
	if "<system><info>" in cmd:
		return ok(
			"<result><system><hostname>PA-DOHA-01</hostname><model>PA-3220</model><serial>016401002345</serial>"
			"<sw-version>10.2.4</sw-version><uptime>520 days, 4:12:09</uptime><app-version>8790-8501</app-version>"
			"</system></result>"
		)
	if "<resources>" in cmd:
		top = (
			"top - 08:00:01 up 520 days,  4:12,  0 users,  load average: 1.10, 1.05, 1.00\n"
			"Tasks: 210 total,   1 running, 209 sleeping,   0 stopped,   0 zombie\n"
			"%Cpu(s): 12.3 us,  3.1 sy,  0.0 ni, 84.0 id,  0.4 wa,  0.0 hi,  0.2 si,  0.0 st\n"
			"MiB Mem :  15925.4 total,   2101.2 free,  12500.8 used,   1323.4 buff/cache\n"
		)
		return ok(f"<result><![CDATA[{top}]]></result>")
	if "<high-availability>" in cmd:
		return ok(
			"<result><enabled>yes</enabled><group><mode>Active-Passive</mode><running-sync>synchronized</running-sync>"
			"<local-info><state>active</state></local-info><peer-info><state>passive</state></peer-info></group></result>"
		)
	if "<license>" in cmd:
		entries = [
			("Threat Prevention", _pan_date(-10), "yes"),
			("WildFire License", _pan_date(400), "no"),
			("Premium Support", _pan_date(45), "no"),
			("PA-3220 Platform", "Never", "no"),
		]
		body = "".join(
			f"<entry><feature>{f}</feature><description>{f}</description><expires>{e}</expires><expired>{x}</expired></entry>"
			for f, e, x in entries
		)
		return ok(f"<result><licenses>{body}</licenses></result>")
	return err("Unknown command")


def _fortios_response(path) -> tuple[int, dict]:
	if path.startswith("/api/v2/monitor/system/status"):
		return 200, {
			"results": {"model_name": "FortiGate", "model_number": "200F", "model": "FGT200F", "hostname": "FGT-DOHA-01"},
			"status": "success", "serial": "FG200FT921900001", "version": "v7.2.8", "build": 1639,
		}
	if path.startswith("/api/v2/monitor/system/resource/usage"):
		return 200, {"results": {"cpu": [{"interval": "1-min", "current": 7}], "mem": [{"interval": "1-min", "current": 91}]}, "status": "success"}
	if path.startswith("/api/v2/monitor/web-ui/state"):
		reboot = int((time.time() - 30 * 86400) * 1000)
		return 200, {"results": {"utc_last_reboot": reboot}, "status": "success"}
	if path.startswith("/api/v2/monitor/system/ha-checksums"):
		return 200, {
			"results": [
				{"serial_no": "FG200FT921900001", "is_manage_master": 1, "checksum": {"all": "a1b2c3d4"}},
				{"serial_no": "FG200FT921900002", "is_manage_master": 0, "checksum": {"all": "ffff0000"}},
			],
			"status": "success",
		}
	if path.startswith("/api/v2/monitor/license/status"):
		return 200, {
			"results": {
				"forticare": {"status": "registered", "expires": _epoch(200)},
				"antivirus": {"status": "licensed", "expires": _epoch(20)},
				"ips": {"status": "licensed", "expires": _epoch(300)},
				"web_filtering": {"status": "no_license"},
			},
			"status": "success",
		}
	return 404, {"status": "error", "http_status": 404}


class _ApiHandler(BaseHTTPRequestHandler):
	kind = "panos"

	def log_message(self, *args):
		pass

	def do_GET(self):
		url = urlparse(self.path)
		if self.kind == "panos" and url.path.rstrip("/") == "/api":
			params = {k: v[0] for k, v in parse_qs(url.query).items()}
			status, body = _panos_response(params)
			self._send(status, body, "application/xml")
		elif self.kind == "fortios":
			if self.headers.get("Authorization") != f"Bearer {API_KEY}":
				self._send(401, json.dumps({"status": "error", "http_status": 401}), "application/json")
				return
			status, body = _fortios_response(self.path)
			self._send(status, json.dumps(body), "application/json")
		else:
			self._send(404, "not found", "text/plain")

	def _send(self, status, body, ctype):
		data = body.encode()
		self.send_response(status)
		self.send_header("Content-Type", ctype)
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)


def _self_signed_cert() -> tuple[str, str]:
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.x509.oid import NameOID

	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hc-lab-device")])
	now = dt.datetime.now(dt.UTC)
	cert = (
		x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
		.serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
		.not_valid_after(now + dt.timedelta(days=3650)).sign(key, hashes.SHA256())
	)
	folder = tempfile.mkdtemp(prefix="hc-lab-")
	cert_path, key_path = os.path.join(folder, "cert.pem"), os.path.join(folder, "key.pem")
	with open(cert_path, "wb") as f:
		f.write(cert.public_bytes(serialization.Encoding.PEM))
	with open(key_path, "wb") as f:
		f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
	return cert_path, key_path


def _serve_https(port, kind, cert_path, key_path):
	handler = type(f"{kind}Handler", (_ApiHandler,), {"kind": kind})
	httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
	context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	context.load_cert_chain(cert_path, key_path)
	httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
	httpd.serve_forever()


def main():
	if not PASSWORD or not API_KEY:
		sys.exit("Set LAB_DEVICE_PASSWORD and LAB_DEVICE_API_KEY (see .env.example)")
	host_key = paramiko.RSAKey.generate(2048)
	cert_path, key_path = _self_signed_cert()
	threads = [threading.Thread(target=_serve_ssh, args=(p, prof, host_key), daemon=True) for p, prof in SSH_DEVICES.items()]
	threads += [
		threading.Thread(target=_serve_https, args=(8443, "panos", cert_path, key_path), daemon=True),
		threading.Thread(target=_serve_https, args=(9443, "fortios", cert_path, key_path), daemon=True),
	]
	for t in threads:
		t.start()
	print("HC lab devices listening: SSH 2201-2204, PAN-OS API 8443, FortiOS API 9443", flush=True)
	while True:
		time.sleep(3600)


if __name__ == "__main__":
	main()
