"""Notification flow engine.

One evaluation function (`evaluate_step`) is shared by the daily scheduler, the "On status change"
hook, the Test Flow dry run and the Notification Timeline, so all four always agree.

De-duplication is driven by HC Notification Log, keyed by
(contract, flow, cycle period_label, step_no, channel), using `run_date <= today` comparisons,
never exact-day equality. A skipped scheduler run is therefore caught up on the next run, and a
second run on the same day sends nothing new.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	escape_html,
	formatdate,
	get_datetime,
	get_url_to_form,
	getdate,
	now_datetime,
)

from hc_tracker.notifications import channels as ch
from hc_tracker.notifications import templates as tpl
from hc_tracker.scheduling import is_working_day, shift_to_working_day, skip_non_working_days
from hc_tracker.utils import (
	CONTRACT_USER_FIELDS,
	get_period_label,
	get_settings,
	get_today,
	split_list,
)

MODE_BEFORE_DUE = "Days before due date"
MODE_AFTER_DUE = "Days after due date (overdue)"
MODE_BEFORE_SCHEDULED = "Days before scheduled date"
MODE_AFTER_PREVIOUS = "Days after previous step if not resolved"
MODE_STATUS = "On status change"
MODE_RESCHEDULE = "On reschedule"
EVENT_MODES = (MODE_STATUS, MODE_RESCHEDULE)

CH_EMAIL = "Email"
CH_TEAMS = "Teams"
CH_SYSTEM = "System Notification"

STATE_SENT = "Sent"
STATE_DUE = "Due"
STATE_PENDING = "Pending"
STATE_SKIPPED = "Skipped"


# ---------------------------------------------------------------------------
# Flow lookup
# ---------------------------------------------------------------------------


def get_flow_for_frequency(frequency: str | None) -> str | None:
	"""Enabled flow for this frequency, else the default flow, else any enabled 'All' flow."""
	if frequency:
		name = frappe.db.get_value(
			"HC Notification Flow",
			{"enabled": 1, "applies_to_frequency": frequency},
			"name",
			order_by="is_default desc, creation asc",
		)
		if name:
			return name
	name = frappe.db.get_value("HC Notification Flow", {"enabled": 1, "is_default": 1}, "name")
	if name:
		return name
	return frappe.db.get_value(
		"HC Notification Flow", {"enabled": 1, "applies_to_frequency": "All"}, "name", order_by="creation asc"
	)


def get_contract_flow(contract):
	name = contract.notification_flow
	if name and not frappe.db.get_value("HC Notification Flow", name, "enabled"):
		name = None
	name = name or get_flow_for_frequency(contract.frequency)
	return frappe.get_doc("HC Notification Flow", name) if name else None


def get_cycle_label(contract) -> str:
	return get_period_label(contract.next_due_date, contract.frequency)


def sorted_steps(flow) -> list:
	return sorted(flow.get("steps") or [], key=lambda s: (cint(s.step_no), s.idx))


# ---------------------------------------------------------------------------
# Notification log lookups
# ---------------------------------------------------------------------------


def get_sent_map(contract_name: str, flow_name: str, cycle_label: str) -> dict:
	"""{step_no: {"first": date, "last": date, "channels": {channel: last run_date}}} of Sent logs."""
	rows = frappe.get_all(
		"HC Notification Log",
		filters={
			"contract": contract_name,
			"flow": flow_name,
			"period_label": cycle_label,
			"status": "Sent",
		},
		fields=["step_no", "channel", "run_date", "sent_on"],
		order_by="run_date asc",
	)
	sent = {}
	for row in rows:
		run_date = getdate(row.run_date)
		entry = sent.setdefault(
			cint(row.step_no), {"first": run_date, "last": run_date, "channels": {}, "sent_on": {}}
		)
		entry["first"] = min(entry["first"], run_date)
		entry["last"] = max(entry["last"], run_date)
		previous = entry["channels"].get(row.channel)
		entry["channels"][row.channel] = max(previous, run_date) if previous else run_date
		sent_on = get_datetime(row.sent_on) if row.sent_on else None
		if sent_on and (row.channel not in entry["sent_on"] or sent_on > entry["sent_on"][row.channel]):
			entry["sent_on"][row.channel] = sent_on
	return sent


def _sent_since(sent: dict | None, since) -> dict | None:
	"""Only the channels sent at/after `since` (used to restart scheduled-date reminders after a reschedule)."""
	if not sent or not since:
		return sent
	since = get_datetime(since)
	channels = {ch: d for ch, d in sent["channels"].items() if sent["sent_on"].get(ch) and sent["sent_on"][ch] >= since}
	if not channels:
		return None
	return {**sent, "channels": channels, "first": min(channels.values()), "last": max(channels.values())}


def get_failure_map(contract_name: str, flow_name: str, cycle_label: str) -> dict:
	rows = frappe.get_all(
		"HC Notification Log",
		filters={
			"contract": contract_name,
			"flow": flow_name,
			"period_label": cycle_label,
			"status": "Failed",
		},
		fields=["step_no", "channel", "error", "run_date"],
		order_by="creation desc",
	)
	failures = {}
	for row in rows:
		failures.setdefault(cint(row.step_no), row)
	return failures


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------


def _user_entry(user: str | None) -> dict | None:
	if not user or user in ("Guest",):
		return None
	row = frappe.db.get_value("User", user, ["name", "email", "enabled", "user_type"], as_dict=True)
	if not row or not cint(row.enabled) or not row.email:
		return None
	return {"email": row.email, "user": row.name if row.user_type == "System User" else None}


def _value_entry(value: str | None) -> dict | None:
	"""A Link User value or a plain email address."""
	if not value:
		return None
	if frappe.db.exists("User", value):
		return _user_entry(value)
	if "@" in value:
		user = frappe.db.get_value("User", {"email": value, "enabled": 1}, "name")
		return _user_entry(user) if user else {"email": value, "user": None}
	return None


def users_with_role(role: str | None) -> list[dict]:
	if not role:
		return []
	users = frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True
	)
	entries = []
	for user in users:
		if user in ("Administrator", "Guest"):
			continue
		entry = _user_entry(user)
		if entry:
			entries.append(entry)
	return entries


def _contract_field_fallback(fieldname: str, settings) -> str | None:
	if fieldname == "technical_manager":
		return settings.default_technical_manager
	if fieldname == "helpdesk_contact":
		return settings.default_helpdesk_email
	return None


def resolve_target(contract, kind, field, role, user, email, settings, fallback_role=None) -> list[dict]:
	entries: list[dict] = []
	if kind == "Contract Field":
		if field in CONTRACT_USER_FIELDS:
			value = contract.get(field) or _contract_field_fallback(field, settings)
			entry = _value_entry(value)
			if entry:
				entries.append(entry)
	elif kind == "Role":
		entries.extend(users_with_role(role))
	elif kind == "Specific User":
		entry = _user_entry(user)
		if entry:
			entries.append(entry)
	elif kind == "Email Address":
		for address in split_list(email):
			entry = _value_entry(address)
			if entry:
				entries.append(entry)
	elif kind == "Client Contact":
		for address in [contract.get("client_contact_email"), *split_list(contract.get("client_cc_emails"))]:
			if address and "@" in address:
				entries.append({"email": address.strip(), "user": None})

	if not entries and fallback_role:
		entries.extend(users_with_role(fallback_role))
	return _dedupe(entries)


def _dedupe(entries: list[dict], exclude: set[str] | None = None) -> list[dict]:
	seen = set(exclude or ())
	out = []
	for entry in entries:
		key = (entry.get("email") or "").lower()
		if key and key not in seen:
			seen.add(key)
			out.append(entry)
	return out


def resolve_recipients(contract, step, settings) -> tuple[list[dict], list[dict]]:
	to = resolve_target(
		contract,
		step.recipient_type,
		step.recipient_field,
		step.recipient_role,
		step.recipient_user,
		step.recipient_email,
		settings,
		fallback_role=step.fallback_role,
	)
	cc = []
	if step.cc_type:
		cc = resolve_target(
			contract, step.cc_type, step.cc_field, step.cc_role, step.cc_user, step.cc_email, settings
		)
	cc = _dedupe(cc, exclude={(e.get("email") or "").lower() for e in to})
	return to, cc


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def expand_channels(step, settings, to: list[dict], cc: list[dict]) -> list[str]:
	"""Concrete channels for a step. Email steps also get the pop-up/bell channel when the step's
	"Also show pop-up" box and HC Settings > Enable pop-up notifications are both on."""
	channel = step.channel or CH_EMAIL
	result = []
	if channel in (CH_EMAIL, "Email + Teams"):
		result.append(CH_EMAIL)
	if channel in (CH_TEAMS, "Email + Teams") and cint(settings.enable_teams):
		result.append(CH_TEAMS)

	has_users = any(e.get("user") for e in to + cc)
	if channel == CH_SYSTEM:
		if has_users:
			result.append(CH_SYSTEM)
	elif cint(step.show_popup) and cint(settings.enable_popup_notifications) and has_users:
		result.append(CH_SYSTEM)
	return result


# ---------------------------------------------------------------------------
# Step evaluation
# ---------------------------------------------------------------------------


def _status_block_reason(step, status: str) -> str | None:
	only_if = split_list(step.only_if_status_in)
	if only_if and status not in only_if:
		return _("Status is {0}; step only fires while status is {1}").format(status, ", ".join(only_if))
	stop_when = split_list(step.stop_when_status)
	if stop_when and status in stop_when:
		return _("Stopped: status is {0}").format(status)
	return None


def _previous_step_no(step, steps) -> int | None:
	if cint(step.after_step_no):
		return cint(step.after_step_no)
	earlier = [cint(s.step_no) for s in steps if cint(s.step_no) < cint(step.step_no)]
	return max(earlier) if earlier else None


def evaluate_step(contract, step, on_date, sent_map, settings, steps=None, status_event=None, reschedule_event=False):
	"""Evaluate one step for one contract on `on_date`.

	Returns a frappe._dict with: state (Sent/Due/Pending/Skipped), reason, planned_date,
	planned_label, to, cc, channels (all), due_channels (still to send), last_sent.
	"""
	on_date = getdate(on_date)
	steps = steps or []
	sent = sent_map.get(cint(step.step_no))
	result = frappe._dict(
		state=STATE_PENDING,
		reason="",
		planned_date=None,
		planned_label="",
		to=[],
		cc=[],
		channels=[],
		due_channels=[],
		last_sent=sent["last"] if sent else None,
	)

	to, cc = resolve_recipients(contract, step, settings)
	result.to, result.cc = to, cc
	result.channels = expand_channels(step, settings, to, cc)

	if not cint(step.enabled):
		result.state, result.reason = STATE_SKIPPED, _("Step disabled")
		return result

	mode = step.trigger_mode
	days = cint(step.trigger_days)
	status = contract.status
	due = getdate(contract.next_due_date) if contract.next_due_date else None

	if mode == MODE_RESCHEDULE:
		result.planned_label = _("When the booked date changes")
		if reschedule_event:
			# Every reschedule notifies again (no once-per-cycle de-duplication)
			result.due_channels = list(result.channels)
			result.planned_date = on_date
			result.state = STATE_DUE if result.channels else STATE_SKIPPED
			result.reason = _("Booked date changed") if result.channels else _("No channel applies")
			return result
		result.state = STATE_SENT if sent else STATE_PENDING
		result.reason = (
			_("Last sent on {0}").format(formatdate(sent["last"])) if sent else _("Waiting for a reschedule")
		)
		return result

	if mode == MODE_STATUS:
		result.planned_label = _("When status becomes {0}").format(step.on_status or "?")
		if status_event and status_event == step.on_status:
			planned = on_date
			status = status_event
		else:
			result.state = STATE_SENT if sent else STATE_PENDING
			result.reason = (
				_("Sent on {0}").format(formatdate(sent["last"])) if sent else _("Waiting for status change")
			)
			return result
	elif not due:
		result.state, result.reason = STATE_SKIPPED, _("Contract has no Next Due Date")
		return result
	elif mode == MODE_BEFORE_DUE:
		planned = add_days(due, -days)
		result.planned_label = _("{0} day(s) before due date").format(days)
	elif mode == MODE_AFTER_DUE:
		planned = add_days(due, days)
		result.planned_label = _("{0} day(s) after due date").format(days)
	elif mode == MODE_BEFORE_SCHEDULED:
		result.planned_label = _("{0} day(s) before scheduled date").format(days)
		if not contract.scheduled_date:
			result.reason = _("No scheduled date yet")
			if sent:
				result.state = STATE_SENT
			return result
		scheduled = getdate(contract.scheduled_date)
		planned = add_days(scheduled, -days)
		# A reschedule restarts the reminders that count back from the booked date
		sent = _sent_since(sent, contract.get("last_rescheduled_on"))
		result.last_sent = sent["last"] if sent else None
		if on_date > scheduled and not sent:
			result.planned_date = getdate(planned)
			result.state, result.reason = STATE_SKIPPED, _("Scheduled date has passed")
			return result
	elif mode == MODE_AFTER_PREVIOUS:
		previous_no = _previous_step_no(step, steps)
		result.planned_label = _("{0} day(s) after step {1}").format(days, previous_no or "?")
		previous = sent_map.get(cint(previous_no)) if previous_no else None
		if not previous:
			result.reason = _("Waiting for step {0} to be sent").format(previous_no or "?")
			return result
		planned = add_days(previous["first"], days)
	else:
		result.state, result.reason = STATE_SKIPPED, _("Unknown trigger mode {0}").format(mode)
		return result

	result.planned_date = getdate(planned)
	if mode not in EVENT_MODES and skip_non_working_days():
		direction = -1 if mode in (MODE_BEFORE_DUE, MODE_BEFORE_SCHEDULED) else 1
		shifted = shift_to_working_day(result.planned_date, direction)
		if shifted != result.planned_date:
			result.planned_label += " " + _("(moved to working day)")
			result.planned_date = shifted

	block = _status_block_reason(step, status)
	if block:
		result.state = STATE_SENT if sent else STATE_SKIPPED
		result.reason = block
		return result

	paused_until = contract.get("reminders_paused_until")
	if (
		mode not in EVENT_MODES
		and paused_until
		and not cint(step.get("ignore_pause"))
		and on_date < getdate(paused_until)
	):
		result.state = STATE_SENT if sent else STATE_PENDING
		result.reason = _("Reminders paused until {0}").format(formatdate(paused_until))
		return result

	if on_date < result.planned_date:
		result.state = STATE_SENT if sent else STATE_PENDING
		result.reason = _("Planned for {0}").format(formatdate(result.planned_date))
		return result

	repeat = cint(step.repeat_every_days)
	sent_channels = sent["channels"] if sent else {}
	for channel in result.channels:
		last = sent_channels.get(channel)
		if last is None or (repeat > 0 and on_date >= add_days(last, repeat)):
			result.due_channels.append(channel)

	if result.due_channels:
		result.state = STATE_DUE
		result.reason = (
			_("Repeat due (every {0} days)").format(repeat) if sent else _("Due since {0}").format(
				formatdate(result.planned_date)
			)
		)
	elif not result.channels:
		result.state, result.reason = STATE_SKIPPED, _("No channel applies (no recipients or Teams disabled)")
	else:
		result.state = STATE_SENT
		result.reason = (
			_("Next repeat on {0}").format(formatdate(add_days(sent["last"], repeat)))
			if repeat > 0 and sent
			else _("Sent on {0}").format(formatdate(sent["last"]))
		)
	return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def build_context(contract, step, flow, on_date, cycle_label, status_event=None, extra=None) -> dict:
	on_date = getdate(on_date)
	due = getdate(contract.next_due_date) if contract.next_due_date else on_date
	days_left = date_diff(due, on_date)
	cycles = contract.get("cycles") or []
	scheduled = getdate(contract.scheduled_date) if contract.scheduled_date else None
	return {
		"doc": contract,
		"step": step,
		"flow": flow,
		"days_left": days_left,
		"days_overdue": max(0, -days_left),
		"due_date": formatdate(due),
		"scheduled_date": formatdate(scheduled) if scheduled else "",
		"days_to_scheduled": date_diff(scheduled, on_date) if scheduled else None,
		"contract_url": get_url_to_form("HC Contract", contract.name),
		"cycle_label": cycle_label,
		"today": formatdate(on_date),
		"event_status": status_event or "",
		"last_cycle": cycles[-1] if cycles else None,
		"old_scheduled_date": "",
		"reschedule_reason": "",
		"reschedule_note": "",
		**(extra or {}),
	}


def render(template: str | None, default: str, context: dict) -> str:
	return frappe.render_template(template or default, context)


def render_step(step, context) -> tuple[str, str]:
	"""Render subject/message in the HC Settings notification language (English / Arabic / both)."""
	language = get_settings().notification_language or "English"

	def english():
		subject = render(step.subject_template, tpl.DEFAULT_SUBJECT, context)
		return subject.strip().replace("\n", " "), render(step.message_template, tpl.DEFAULT_MESSAGE, context)

	def arabic():
		previous_lang = frappe.local.lang
		frappe.local.lang = "ar"  # so {{ _(...) }} in the templates renders Arabic
		try:
			subject = render(step.get("subject_template_ar"), tpl.DEFAULT_SUBJECT_AR, context)
			message = render(step.get("message_template_ar"), tpl.DEFAULT_MESSAGE_AR, context)
		finally:
			frappe.local.lang = previous_lang
		return subject.strip().replace("\n", " "), message

	if language == "Arabic":
		subject, message = arabic()
		message = tpl.rtl(message)
	elif language == "English + Arabic":
		subject_en, message_en = english()
		subject_ar, message_ar = arabic()
		subject = f"{subject_en} | {subject_ar}"
		message = tpl.bilingual(message_en, message_ar)
	else:
		subject, message = english()
	return subject[:900], message


# ---------------------------------------------------------------------------
# Delivery + logging
# ---------------------------------------------------------------------------


def write_log(
	*,
	contract_name,
	flow_name,
	step_no,
	step_label,
	cycle_label,
	channel,
	to,
	cc,
	subject,
	status,
	error=None,
	run_date=None,
):
	log = frappe.new_doc("HC Notification Log")
	log.update(
		{
			"contract": contract_name,
			"flow": flow_name,
			"step_no": cint(step_no),
			"step_label": step_label,
			"period_label": cycle_label,
			"channel": channel,
			"recipients": ", ".join(to),
			"cc": ", ".join(cc),
			"subject": subject,
			"sent_on": now_datetime(),
			"run_date": getdate(run_date) if run_date else get_today(),
			"status": status,
			"error": error,
		}
	)
	log.insert(ignore_permissions=True)
	return log


def deliver_channel(channel, *, to, cc, subject, message, contract, step, settings, indicator="blue"):
	if channel == CH_EMAIL:
		ch.send_email(ch.emails_only(to), ch.emails_only(cc), subject, message, contract.name)
	elif channel == CH_TEAMS:
		webhook = (step.teams_webhook_url or "").strip() or (settings.default_teams_webhook_url or "").strip()
		facts = [
			(_("Client"), f"{contract.client_name} ({contract.client_id})"),
			(_("Due date"), formatdate(contract.next_due_date)),
			(_("Status"), contract.status),
			(_("Engineer"), contract.engineer_name or contract.assigned_engineer),
			(_("Step"), f"{step.step_no}. {step.step_label}"),
		]
		payload = ch.build_adaptive_card(
			subject,
			ch.html_to_text(message),
			facts,
			url=get_url_to_form("HC Contract", contract.name),
			color="Attention" if indicator == "red" else "Accent",
		)
		ch.post_to_teams(webhook, payload)
	elif channel == CH_SYSTEM:
		ch.send_system_notification(ch.users_only(to + cc), subject, message, contract.name, indicator)
	else:
		raise ch.DeliveryError(_("Unknown channel {0}").format(channel))


def send_step(
	contract, flow, step, evaluation, on_date, cycle_label, settings, status_event=None, extra_context=None
) -> list:
	"""Send every due channel of a step and record one HC Notification Log row per channel."""
	context = build_context(contract, step, flow, on_date, cycle_label, status_event, extra_context)
	indicator = "red" if step.trigger_mode == MODE_AFTER_DUE else "blue"
	to_emails = ch.emails_only(evaluation.to)
	cc_emails = ch.emails_only(evaluation.cc)
	logs = []

	try:
		subject, message = render_step(step, context)
	except Exception:
		subject, message = step.step_label, ""
		for channel in evaluation.due_channels:
			logs.append(
				write_log(
					contract_name=contract.name,
					flow_name=flow.name,
					step_no=step.step_no,
					step_label=step.step_label,
					cycle_label=cycle_label,
					channel=channel,
					to=to_emails,
					cc=cc_emails,
					subject=subject,
					status="Failed",
					error=_("Template error:\n") + frappe.get_traceback(),
					run_date=on_date,
				)
			)
		return logs

	for channel in evaluation.due_channels:
		savepoint = "hc_tracker_send"
		frappe.db.savepoint(savepoint)
		try:
			deliver_channel(
				channel,
				to=evaluation.to,
				cc=evaluation.cc,
				subject=subject,
				message=message,
				contract=contract,
				step=step,
				settings=settings,
				indicator=indicator,
			)
			status, error = "Sent", None
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			status = "Failed"
			error = str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()

		recipients = to_emails if channel != CH_SYSTEM else ch.users_only(evaluation.to + evaluation.cc)
		logs.append(
			write_log(
				contract_name=contract.name,
				flow_name=flow.name,
				step_no=step.step_no,
				step_label=step.step_label,
				cycle_label=cycle_label,
				channel=channel,
				to=recipients,
				cc=cc_emails if channel == CH_EMAIL else [],
				subject=subject,
				status=status,
				error=error,
				run_date=on_date,
			)
		)
	return logs


def _mark_sent(sent_map, step_no, on_date, logs):
	for log in logs:
		if log.status != "Sent":
			continue
		entry = sent_map.setdefault(cint(step_no), {"first": on_date, "last": on_date, "channels": {}})
		entry["last"] = max(entry["last"], on_date)
		entry["channels"][log.channel] = on_date


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def process_contract(contract, on_date=None) -> int:
	"""Evaluate all date-based steps for one contract and send what is due. Returns logs written."""
	on_date = get_today(on_date)
	flow = get_contract_flow(contract)
	if not flow:
		return 0
	if skip_non_working_days() and not is_working_day(on_date):
		return 0  # nothing is sent on weekends/holidays; the <= checks catch up on the next working day
	settings = get_settings()
	cycle_label = get_cycle_label(contract)
	sent_map = get_sent_map(contract.name, flow.name, cycle_label)
	steps = sorted_steps(flow)
	written = 0
	for step in steps:
		if step.trigger_mode == MODE_RESCHEDULE:
			continue
		if step.trigger_mode == MODE_STATUS:
			written += _retry_failed_status_step(contract, flow, step, steps, on_date, cycle_label, sent_map, settings)
			continue
		evaluation = evaluate_step(contract, step, on_date, sent_map, settings, steps)
		if evaluation.state != STATE_DUE:
			continue
		logs = send_step(contract, flow, step, evaluation, on_date, cycle_label, settings)
		_mark_sent(sent_map, step.step_no, on_date, logs)
		written += len(logs)
	return written


def _retry_failed_status_step(contract, flow, step, steps, on_date, cycle_label, sent_map, settings) -> int:
	"""Daily retry for an 'On status change' step whose channel failed (e.g. no email account yet),
	as long as the contract is still in that status and the channel never succeeded this cycle."""
	if not cint(step.enabled) or step.on_status != contract.status:
		return 0
	failed = set(
		frappe.get_all(
			"HC Notification Log",
			filters={
				"contract": contract.name,
				"flow": flow.name,
				"period_label": cycle_label,
				"step_no": cint(step.step_no),
				"status": "Failed",
			},
			pluck="channel",
		)
	)
	if not failed:
		return 0
	evaluation = evaluate_step(contract, step, on_date, sent_map, settings, steps, status_event=step.on_status)
	evaluation.due_channels = [c for c in evaluation.due_channels if c in failed]
	if evaluation.state != STATE_DUE or not evaluation.due_channels:
		return 0
	logs = send_step(contract, flow, step, evaluation, on_date, cycle_label, settings, status_event=step.on_status)
	_mark_sent(sent_map, step.step_no, on_date, logs)
	return len(logs)


def fire_reschedule(contract, old_date=None, reason=None, note=None) -> int:
	"""Send 'On reschedule' steps (called from HCContract.on_update when the booked date changes)."""
	flow = get_contract_flow(contract)
	if not flow:
		return 0
	on_date = get_today()
	settings = get_settings()
	cycle_label = get_cycle_label(contract)
	steps = sorted_steps(flow)
	extra = {
		"old_scheduled_date": formatdate(old_date) if old_date else "",
		"reschedule_reason": reason or "",
		"reschedule_note": note or "",
	}
	written = 0
	for step in steps:
		if step.trigger_mode != MODE_RESCHEDULE:
			continue
		evaluation = evaluate_step(contract, step, on_date, {}, settings, steps, reschedule_event=True)
		if evaluation.state != STATE_DUE:
			continue
		written += len(send_step(contract, flow, step, evaluation, on_date, cycle_label, settings, extra_context=extra))
	return written


def fire_status_change(contract, new_status: str, cycle_label: str | None = None) -> int:
	"""Send "On status change" steps for `new_status` (called from HCContract.on_update)."""
	flow = get_contract_flow(contract)
	if not flow:
		return 0
	on_date = get_today()
	settings = get_settings()
	cycle_label = cycle_label or get_cycle_label(contract)
	sent_map = get_sent_map(contract.name, flow.name, cycle_label)
	steps = sorted_steps(flow)
	written = 0
	for step in steps:
		if step.trigger_mode != MODE_STATUS or step.on_status != new_status:
			continue
		evaluation = evaluate_step(
			contract, step, on_date, sent_map, settings, steps, status_event=new_status
		)
		if evaluation.state != STATE_DUE:
			continue
		logs = send_step(
			contract, flow, step, evaluation, on_date, cycle_label, settings, status_event=new_status
		)
		_mark_sent(sent_map, step.step_no, on_date, logs)
		written += len(logs)
	return written


# ---------------------------------------------------------------------------
# Dry run ("Test Flow" button) and timeline rendering
# ---------------------------------------------------------------------------

_STATE_COLORS = {
	STATE_SENT: "green",
	STATE_DUE: "orange",
	STATE_PENDING: "blue",
	STATE_SKIPPED: "gray",
}


def _pill(label: str, color: str) -> str:
	return f'<span class="indicator-pill {color}">{escape_html(label)}</span>'


def _people(entries: list[dict]) -> str:
	if not entries:
		return '<span class="text-muted">-</span>'
	return "<br>".join(escape_html(e["email"]) for e in entries)


def evaluate_flow(contract, flow, on_date=None) -> list[dict]:
	on_date = get_today(on_date)
	settings = get_settings()
	cycle_label = get_cycle_label(contract)
	sent_map = get_sent_map(contract.name, flow.name, cycle_label)
	failures = get_failure_map(contract.name, flow.name, cycle_label)
	steps = sorted_steps(flow)
	rows = []
	for step in steps:
		evaluation = evaluate_step(contract, step, on_date, sent_map, settings, steps)
		subject = ""
		try:
			context = build_context(contract, step, flow, on_date, cycle_label)
			subject, _message = render_step(step, context)
		except Exception as e:
			subject = _("Template error: {0}").format(e)
		failure = failures.get(cint(step.step_no))
		rows.append(
			{
				"step": step,
				"evaluation": evaluation,
				"subject": subject,
				"failure": failure,
			}
		)
	return rows


def render_rows_html(rows, title_html: str, dry_run: bool) -> str:
	head = [_("#"), _("Step"), _("Trigger"), _("Planned"), _("To"), _("CC"), _("Channels"), _("Status")]
	if dry_run:
		head.append(_("Subject"))
	html = [title_html, '<div class="table-responsive"><table class="table table-bordered table-sm" style="font-size:12px">']
	html.append("<thead><tr>" + "".join(f"<th>{escape_html(h)}</th>" for h in head) + "</tr></thead><tbody>")
	for row in rows:
		step, ev = row["step"], row["evaluation"]
		state = ev.state
		if dry_run:
			label = _("Would send today") if state == STATE_DUE else state
		else:
			label = _("Pending (sends at next run)") if state == STATE_DUE else state
		status_html = _pill(label, _STATE_COLORS.get(state, "gray"))
		if ev.reason:
			status_html += f'<div class="text-muted small">{escape_html(ev.reason)}</div>'
		if row.get("failure") and state != STATE_SENT:
			status_html += '<div class="small text-danger">{}</div>'.format(
				escape_html(_("Last attempt failed ({0})").format(row["failure"].channel))
			)
		channels = ev.due_channels if (dry_run and state == STATE_DUE) else ev.channels
		cells = [
			escape_html(str(step.step_no)),
			escape_html(step.step_label or ""),
			escape_html(ev.planned_label or step.trigger_mode or ""),
			escape_html(formatdate(ev.planned_date)) if ev.planned_date else "-",
			_people(ev.to),
			_people(ev.cc),
			escape_html(", ".join(channels) or "-"),
			status_html,
		]
		if dry_run:
			cells.append(escape_html(row.get("subject") or ""))
		html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
	html.append("</tbody></table></div>")
	return "".join(html)


@frappe.whitelist()
def dry_run(flow: str, contract: str, on_date: str | None = None) -> dict:
	"""Show which steps of `flow` would fire for `contract` on `on_date`, without sending."""
	frappe.only_for(("System Manager", "HC Technical Manager"))
	flow_doc = frappe.get_doc("HC Notification Flow", flow)
	contract_doc = frappe.get_doc("HC Contract", contract)
	on_date = get_today(on_date)
	rows = evaluate_flow(contract_doc, flow_doc, on_date)
	would_send = [r for r in rows if r["evaluation"].state == STATE_DUE]
	title = (
		"<p><b>{}</b> - {} ({}) - {}: <b>{}</b> - {}: {} - {}: {}</p>"
		"<p class='text-muted small'>{}</p>"
	).format(
		escape_html(flow_doc.name),
		escape_html(contract_doc.client_name or ""),
		escape_html(contract_doc.name),
		escape_html(_("Cycle")),
		escape_html(get_cycle_label(contract_doc)),
		escape_html(_("Status")),
		escape_html(contract_doc.status or ""),
		escape_html(_("Evaluated as of")),
		escape_html(formatdate(on_date)),
		escape_html(
			_("Dry run: nothing is sent and nothing is logged. {0} step(s) would send today.").format(
				len(would_send)
			)
		),
	)
	return {
		"html": render_rows_html(rows, title, dry_run=True),
		"would_send": [
			{
				"step_no": r["step"].step_no,
				"step_label": r["step"].step_label,
				"to": ch.emails_only(r["evaluation"].to),
				"cc": ch.emails_only(r["evaluation"].cc),
				"channels": r["evaluation"].due_channels,
				"subject": r["subject"],
			}
			for r in would_send
		],
	}


def get_timeline_html(contract) -> str:
	"""HTML for the Notification Timeline field on HC Contract."""
	if contract.is_new() or not contract.next_due_date:
		return '<p class="text-muted">{}</p>'.format(
			escape_html(_("Save the contract with a Next Due Date to see its notification timeline."))
		)
	flow = get_contract_flow(contract)
	if not flow:
		return '<p class="text-muted">{}</p>'.format(
			escape_html(_("No enabled HC Notification Flow applies to this contract."))
		)
	rows = evaluate_flow(contract, flow)
	title = "<p>{}: <b>{}</b> - {}: <b>{}</b></p>".format(
		escape_html(_("Flow")),
		escape_html(flow.name),
		escape_html(_("Cycle")),
		escape_html(get_cycle_label(contract)),
	)
	return render_rows_html(rows, title, dry_run=False)
