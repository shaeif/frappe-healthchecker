"""Phase 2: automated health-check data collection (Frappe side).

Flow: enqueue_collection() creates an HC Collection Run and enqueues run_collection() on the "long"
queue. The job decrypts device credentials, collects every enabled device in parallel (Netmiko /
PAN-OS XML API / FortiOS REST API), evaluates findings, stores per-device results on the run and on
the contract's HC Device rows, attaches a ZIP of raw outputs and a draft PDF report, and notifies
the user who started it and the assigned engineer (pop-up + bell).
"""

import io
import json
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime, get_url_to_form, getdate, now_datetime, today

from hc_tracker.collectors.base import DeviceSpec, clean_extra_commands, is_read_only_command
from hc_tracker.collectors.platforms import get_plan
from hc_tracker.collectors.rules import Thresholds, evaluate, findings_text
from hc_tracker.collectors.runner import collect_all
from hc_tracker.utils import ROLE_ACCOUNT_MANAGER, ROLE_ENGINEER, get_period_label, get_settings, is_full_access, user_roles

ACTIVE_STATUSES = ("Queued", "Running")
REPORT_TEMPLATE = "hc_tracker/templates/hc_collection_report.html"


# ---------------------------------------------------------------------------
# Start a collection
# ---------------------------------------------------------------------------


def can_collect(contract, user=None) -> bool:
	user = user or frappe.session.user
	if is_full_access(user):
		return True
	roles = user_roles(user)
	return (ROLE_ENGINEER in roles and contract.assigned_engineer == user) or (
		ROLE_ACCOUNT_MANAGER in roles and contract.account_manager == user
	)


@frappe.whitelist()
def enqueue_collection(contract: str) -> str:
	doc = frappe.get_doc("HC Contract", contract)
	doc.check_permission("read")
	if not can_collect(doc):
		frappe.throw(_("Only the assigned engineer, the account manager or a Technical Manager can collect device data."), frappe.PermissionError)
	return start_run(doc, frappe.session.user)


def start_run(contract, triggered_by: str) -> str:
	settings = get_settings()
	if not cint(settings.enable_device_collection):
		frappe.throw(_("Device data collection is disabled in HC Settings."))
	if not [d for d in contract.get("devices") or [] if cint(d.enabled)]:
		frappe.throw(_("Add at least one enabled device on the Devices tab first."))
	running = frappe.db.exists("HC Collection Run", {"contract": contract.name, "status": ["in", ACTIVE_STATUSES]})
	if running:
		frappe.throw(_("A collection is already running for this contract: {0}").format(running))

	run = frappe.new_doc("HC Collection Run")
	run.update(
		{
			"contract": contract.name,
			"client_name": contract.client_name,
			"period_label": get_period_label(contract.next_due_date, contract.frequency),
			"status": "Queued",
			"triggered_by": triggered_by,
		}
	)
	run.insert(ignore_permissions=True)
	frappe.enqueue(
		"hc_tracker.collectors.jobs.run_collection",
		queue="long",
		timeout=3600,
		run_name=run.name,
		enqueue_after_commit=True,
	)
	return run.name


def run_auto_collections(on_date=None) -> int:
	"""Daily job: collect for contracts booked for today (HC Settings > Auto Collect On Scheduled Date)."""
	settings = get_settings()
	if not (cint(settings.enable_device_collection) and cint(settings.auto_collect_on_scheduled_date)):
		return 0
	on_date = getdate(on_date or today())
	started = 0
	for name in frappe.get_all(
		"HC Contract",
		filters={"scheduled_date": on_date, "status": ["in", ["Scheduled", "In progress"]]},
		pluck="name",
	):
		contract = frappe.get_doc("HC Contract", name)
		if not [d for d in contract.devices if cint(d.enabled)]:
			continue
		if frappe.db.exists("HC Collection Run", {"contract": name, "creation": [">=", str(on_date)]}):
			continue
		try:
			start_run(contract, "Administrator")
			started += 1
		except frappe.ValidationError:
			frappe.clear_last_message()
	return started


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------


def build_specs(contract, settings) -> list[DeviceSpec]:
	timeout = cint(settings.device_timeout) or 60
	specs = []
	for row in contract.get("devices") or []:
		if not cint(row.enabled):
			continue
		plan = get_plan(row.vendor)
		specs.append(
			DeviceSpec(
				row_name=row.name,
				hostname=row.hostname,
				host=(row.ip_address or row.hostname or "").strip(),
				vendor=row.vendor,
				method=row.connection_method or plan["default_method"],
				port=cint(row.port) or None,
				username=row.username,
				password=row.get_password("password", raise_exception=False),
				secret=row.get_password("enable_secret", raise_exception=False),
				api_key=row.get_password("api_key", raise_exception=False),
				verify_ssl=bool(cint(row.verify_ssl)),
				timeout=timeout,
				extra_commands=[c for c in clean_extra_commands(row.extra_commands) if is_read_only_command(c)],
			)
		)
	return specs


def run_collection(run_name: str):
	run = frappe.get_doc("HC Collection Run", run_name)
	contract = frappe.get_doc("HC Contract", run.contract)
	settings = get_settings()
	run.db_set({"status": "Running", "started_on": now_datetime()})
	frappe.db.commit()

	try:
		specs = build_specs(contract, settings)

		def progress(done, total, result):
			frappe.publish_progress(
				done * 100 / total,
				title=_("Collecting device data"),
				doctype="HC Contract",
				docname=contract.name,
				description=_("{0}/{1}: {2} - {3}").format(done, total, result.hostname, result.status),
			)

		results = collect_all(specs, cint(settings.collection_parallelism) or 4, progress)
		thresholds = Thresholds(
			cpu=flt(settings.cpu_threshold) or 80,
			memory=flt(settings.memory_threshold) or 85,
			uptime_days=cint(settings.uptime_threshold_days) or 365,
			license_days=cint(settings.license_warning_days) or 60,
		)
		findings = evaluate(results, thresholds, getdate(today()))
		summary = findings_text(findings)

		update_device_rows(results)
		fill_run(run, results, findings, summary)
		run.raw_output_file = save_file(run, f"{run.name}-raw-output.zip", build_zip(results), is_private=1)
		run.report_file = save_file(run, f"{run.name}-hc-report.pdf", build_pdf(run, contract, results, findings), is_private=1)
		run.finished_on = now_datetime()
		run.save(ignore_permissions=True)

		if cint(settings.fill_findings_summary) and not frappe.db.get_value("HC Contract", contract.name, "findings_summary"):
			frappe.db.set_value("HC Contract", contract.name, "findings_summary", summary, update_modified=False)
		frappe.db.commit()
		notify(run, contract)
	except Exception:
		frappe.db.rollback()
		run.reload()
		run.db_set({"status": "Failed", "finished_on": now_datetime(), "error": frappe.get_traceback()})
		frappe.db.commit()
		frappe.log_error(title=f"HC Tracker: collection failed for {run.contract}")
		notify(run, contract)
	finally:
		frappe.publish_realtime("hc_collection_done", {"run": run.name, "contract": contract.name}, doctype="HC Contract", docname=contract.name)
		frappe.publish_realtime("hc_collection_done", {"run": run.name, "contract": contract.name}, doctype="HC Collection Run", docname=run.name)


def update_device_rows(results):
	now = now_datetime()
	for r in results:
		values = {"last_status": r.status, "last_collected_on": now, "last_error": (r.error or "")[:1000] or None}
		if r.status != "Failed":
			f = r.facts
			values.update(
				{
					"software_version": f.get("software_version"),
					"serial_number": f.get("serial_number"),
					"uptime_text": f.get("uptime_text"),
					# Percent columns are NOT NULL: 0 means "not reported by this platform"
					"cpu_percent": f.get("cpu_percent") or 0,
					"memory_percent": f.get("memory_percent") or 0,
				}
			)
			if f.get("model"):
				values["model"] = f["model"]
		frappe.db.set_value("HC Device", r.row_name, values, update_modified=False)


def fill_run(run, results, findings, summary):
	run.set("results", [])
	for r in results:
		f = r.facts
		ha = " ".join(str(x) for x in (f.get("ha_mode"), f.get("ha_state")) if x)
		if f.get("ha_in_sync") is not None:
			ha += " (in sync)" if f["ha_in_sync"] else " (OUT OF SYNC)"
		run.append(
			"results",
			{
				"hostname": r.hostname,
				"ip_address": r.host,
				"vendor": r.vendor,
				"method": r.method,
				"status": r.status,
				"software_version": f.get("software_version"),
				"model": f.get("model"),
				"serial_number": f.get("serial_number"),
				"uptime_text": f.get("uptime_text"),
				"cpu_percent": f.get("cpu_percent") or 0,
				"memory_percent": f.get("memory_percent") or 0,
				"ha_state": ha.strip() or None,
				"duration": r.duration,
				"device_row": r.row_name,
				"error": r.error,
			},
		)
	run.set("findings", [x.as_dict() for x in findings])
	ok = len([r for r in results if r.status != "Failed"])
	run.devices_total = len(results)
	run.devices_ok = ok
	run.devices_failed = len(results) - ok
	run.critical_count = len([x for x in findings if x.severity == "Critical"])
	run.warning_count = len([x for x in findings if x.severity == "Warning"])
	run.findings_summary = summary
	run.status = "Completed" if ok == len(results) and not any(r.status == "Partial" for r in results) else (
		"Failed" if ok == 0 else "Partial"
	)


def _safe(name: str) -> str:
	return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "device")[:80]


def build_zip(results) -> bytes:
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for r in results:
			folder = _safe(r.hostname)
			summary = {
				"hostname": r.hostname, "host": r.host, "vendor": r.vendor, "method": r.method, "status": r.status,
				"facts": r.facts, "command_errors": r.command_errors, "error": r.error, "duration": r.duration,
			}
			zf.writestr(f"{folder}/_summary.json", json.dumps(summary, indent=1, default=str))
			for command, output in r.outputs.items():
				zf.writestr(f"{folder}/{_safe(command)}.txt", output)
	return buffer.getvalue()


def build_pdf(run, contract, results, findings) -> bytes:
	from frappe.utils.pdf import get_pdf

	html = frappe.render_template(
		REPORT_TEMPLATE,
		{
			"run": run,
			"contract": contract,
			"results": results,
			"findings": [x.as_dict() for x in findings],
			"generated_on": format_datetime(now_datetime()),
			"engineer": contract.engineer_name or contract.assigned_engineer or "",
			"lic_rows": [(r.hostname, lic) for r in results for lic in (r.facts.get("licenses") or [])],
		},
	)
	return get_pdf(html, {"orientation": "Landscape"})


def save_file(run, file_name: str, content: bytes, is_private=1) -> str:
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": content,
			"is_private": is_private,
			"attached_to_doctype": "HC Collection Run",
			"attached_to_name": run.name,
			"folder": "Home/Attachments",
		}
	)
	file.insert(ignore_permissions=True)
	return file.file_url


def notify(run, contract):
	from hc_tracker.notifications.channels import send_system_notification

	users = {u for u in (run.triggered_by, contract.assigned_engineer) if u and u not in ("Administrator", "Guest")}
	if not users:
		return
	run.reload()
	subject = _("[HC] Device data {0}: {1} ({2} critical, {3} warnings)").format(
		run.status.lower(), contract.client_name, run.critical_count or 0, run.warning_count or 0
	)
	message = _("<p>Collection run <a href='{0}'>{1}</a> finished with status <b>{2}</b>: {3}/{4} devices collected.</p><pre>{5}</pre>").format(
		get_url_to_form("HC Collection Run", run.name), run.name, run.status, run.devices_ok or 0, run.devices_total or 0,
		frappe.utils.escape_html(run.findings_summary or run.error or "")[:3000],
	)
	try:
		send_system_notification(list(users), subject, message, contract.name, "red" if run.critical_count else "green")
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="HC Tracker: collection notification failed")
