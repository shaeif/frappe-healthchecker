"""Notification rule engine.

One evaluation function (`evaluate_step`) is shared by the daily scheduler, the cycle/visit event hooks,
the Test Rules dry run and the AMC's Notification Timeline, so all four always agree.

Two kinds of rules:
* AMC rules (due-date, overdue, after-previous-step, cycle status change) are evaluated once per AMC cycle.
* Visit rules (days before visit date, visit scheduled / rescheduled / report submitted) are evaluated
  once per PM Visit of the cycle.

De-duplication is driven by AMC Notification Log, keyed by (AMC, rule set, cycle, step, channel, PM Visit),
using `run_date <= today` comparisons, never exact-day equality. A skipped scheduler run is therefore caught
up on the next run, and a second run on the same day sends nothing new.
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

from amc_tracker.cycle import cycle_label_of, get_cycle_visits
from amc_tracker.notifications import channels as ch
from amc_tracker.notifications import templates as tpl
from amc_tracker.scheduling import is_working_day, shift_to_working_day, skip_non_working_days
from amc_tracker.utils import (
	AMC_USER_FIELDS,
	VISIT_SCHEDULED,
	VISIT_TO_SCHEDULE,
	get_settings,
	get_today,
	split_list,
)

MODE_BEFORE_DUE = "Days before due date"
MODE_AFTER_DUE = "Days after due date (overdue)"
MODE_AFTER_PREVIOUS = "Days after previous step if not resolved"
MODE_STATUS = "On cycle status change"
MODE_BEFORE_VISIT = "Days before visit date"
MODE_VISIT_ASSIGNED = "On visit assigned"
MODE_VISIT_SCHEDULED = "On visit scheduled"
MODE_VISIT_RESCHEDULED = "On visit rescheduled"
MODE_VISIT_REPORTED = "On visit report submitted"
VISIT_EVENT_MODES = (MODE_VISIT_ASSIGNED, MODE_VISIT_SCHEDULED, MODE_VISIT_RESCHEDULED, MODE_VISIT_REPORTED)
VISIT_MODES = (MODE_BEFORE_VISIT, *VISIT_EVENT_MODES)
EVENT_MODES = (MODE_STATUS, *VISIT_EVENT_MODES)

CH_EMAIL = "Email"
CH_TEAMS = "Teams"
CH_SYSTEM = "System Notification"

STATE_SENT = "Sent"
STATE_DUE = "Due"
STATE_PENDING = "Pending"
STATE_SKIPPED = "Skipped"


# ---------------------------------------------------------------------------
# Rule set lookup
# ---------------------------------------------------------------------------


def get_flow_for_frequency(frequency: str | None) -> str | None:
	"""Enabled rule set for this frequency, else the default, else any enabled 'All' rule set."""
	if frequency:
		name = frappe.db.get_value(
			"AMC Notification Flow",
			{"enabled": 1, "applies_to_frequency": frequency},
			"name",
			order_by="is_default desc, creation asc",
		)
		if name:
			return name
	name = frappe.db.get_value("AMC Notification Flow", {"enabled": 1, "is_default": 1}, "name")
	if name:
		return name
	return frappe.db.get_value(
		"AMC Notification Flow", {"enabled": 1, "applies_to_frequency": "All"}, "name", order_by="creation asc"
	)


def get_amc_flow(amc):
	name = amc.notification_flow
	if name and not frappe.db.get_value("AMC Notification Flow", name, "enabled"):
		name = None
	name = name or get_flow_for_frequency(amc.frequency)
	return frappe.get_doc("AMC Notification Flow", name) if name else None


def sorted_steps(flow) -> list:
	return sorted(flow.get("steps") or [], key=lambda s: (cint(s.step_no), s.idx))


def is_visit_step(step) -> bool:
	return step.trigger_mode in VISIT_MODES


# ---------------------------------------------------------------------------
# Notification log lookups
# ---------------------------------------------------------------------------


def get_sent_map(amc_name: str, flow_name: str, cycle_label: str, visit: str | None = None) -> dict:
	"""{step_no: {"first", "last", "channels": {channel: last run_date}, "sent_on": {...}}} of Sent logs."""
	filters = {"amc": amc_name, "flow": flow_name, "period_label": cycle_label, "status": "Sent"}
	filters["pm_visit"] = visit if visit else ["is", "not set"]
	sent = {}
	for row in frappe.get_all(
		"AMC Notification Log", filters=filters, fields=["step_no", "channel", "run_date", "sent_on"], order_by="run_date asc"
	):
		run_date = getdate(row.run_date)
		entry = sent.setdefault(cint(row.step_no), {"first": run_date, "last": run_date, "channels": {}, "sent_on": {}})
		entry["first"] = min(entry["first"], run_date)
		entry["last"] = max(entry["last"], run_date)
		previous = entry["channels"].get(row.channel)
		entry["channels"][row.channel] = max(previous, run_date) if previous else run_date
		sent_on = get_datetime(row.sent_on) if row.sent_on else None
		if sent_on and (row.channel not in entry["sent_on"] or sent_on > entry["sent_on"][row.channel]):
			entry["sent_on"][row.channel] = sent_on
	return sent


def _sent_since(sent: dict | None, since) -> dict | None:
	"""Only the channels sent at/after `since` (restarts visit-date reminders after a reschedule)."""
	if not sent or not since:
		return sent
	since = get_datetime(since)
	channels = {c: d for c, d in sent["channels"].items() if sent["sent_on"].get(c) and sent["sent_on"][c] >= since}
	if not channels:
		return None
	return {**sent, "channels": channels, "first": min(channels.values()), "last": max(channels.values())}


def get_failure_map(amc_name: str, flow_name: str, cycle_label: str) -> dict:
	rows = frappe.get_all(
		"AMC Notification Log",
		filters={"amc": amc_name, "flow": flow_name, "period_label": cycle_label, "status": "Failed"},
		fields=["step_no", "channel", "error", "run_date", "pm_visit"],
		order_by="creation desc",
	)
	failures = {}
	for row in rows:
		failures.setdefault((cint(row.step_no), row.pm_visit or None), row)
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
	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True)
	entries = []
	for user in users:
		if user in ("Administrator", "Guest"):
			continue
		entry = _user_entry(user)
		if entry:
			entries.append(entry)
	return entries


def _amc_field_fallback(fieldname: str, settings) -> str | None:
	if fieldname == "technical_manager":
		return settings.default_technical_manager
	if fieldname == "helpdesk_contact":
		return settings.default_helpdesk_email
	return None


class Context:
	"""Everything a rule needs about one AMC cycle (and optionally one of its visits), loaded once."""

	def __init__(self, amc, visit=None):
		self.amc = amc
		self.visit = visit
		self.cycle_label = cycle_label_of(amc)
		self._visits = None
		self._client = None

	@property
	def visits(self) -> list:
		if self._visits is None:
			self._visits = get_cycle_visits(self.amc.name, self.cycle_label)
		return self._visits

	@property
	def client(self):
		if self._client is None:
			self._client = (
				frappe.db.get_value(
					"Client",
					self.amc.client,
					["name", "client_name", "contact_name", "contact_email", "contact_phone", "cc_emails"],
					as_dict=True,
				)
				or frappe._dict()
			)
		return self._client

	def engineers(self, only_unscheduled=False) -> list[str]:
		visits = [v for v in self.visits if not only_unscheduled or v.status == VISIT_TO_SCHEDULE]
		if visits or only_unscheduled:
			return list(dict.fromkeys(v.engineer for v in visits))
		return list(dict.fromkeys(r.engineer for r in self.amc.get("engineers") or []))


def resolve_target(ctx: Context, kind, field, role, user, email, settings, fallback_role=None) -> list[dict]:
	entries: list[dict] = []
	if kind == "AMC Field":
		if field in AMC_USER_FIELDS:
			entry = _value_entry(ctx.amc.get(field) or _amc_field_fallback(field, settings))
			if entry:
				entries.append(entry)
	elif kind == "Visit Engineer":
		if ctx.visit:
			entry = _user_entry(ctx.visit.engineer)
			if entry:
				entries.append(entry)
	elif kind == "Cycle Engineers":
		entries.extend(e for e in map(_user_entry, ctx.engineers()) if e)
	elif kind == "Engineers Yet To Schedule":
		entries.extend(e for e in map(_user_entry, ctx.engineers(only_unscheduled=True)) if e)
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
		for address in [ctx.client.get("contact_email"), *split_list(ctx.client.get("cc_emails"))]:
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


def resolve_recipients(ctx: Context, step, settings) -> tuple[list[dict], list[dict]]:
	to = resolve_target(
		ctx, step.recipient_type, step.recipient_field, step.recipient_role, step.recipient_user,
		step.recipient_email, settings, fallback_role=step.fallback_role,
	)
	cc = []
	if step.cc_type:
		cc = resolve_target(ctx, step.cc_type, step.cc_field, step.cc_role, step.cc_user, step.cc_email, settings)
	cc = _dedupe(cc, exclude={(e.get("email") or "").lower() for e in to})
	return to, cc


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def expand_channels(step, settings, to: list[dict], cc: list[dict]) -> list[str]:
	"""Concrete channels for a step. Email rules also get the pop-up/bell channel when the rule's
	"Also show pop-up" box and AMC Settings > Enable pop-up notifications are both on."""
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
		return _("Cycle status is {0}; rule only applies while it is {1}").format(_(status), ", ".join(_(s) for s in only_if))
	stop_when = split_list(step.stop_when_status)
	if stop_when and status in stop_when:
		return _("Stopped: cycle status is {0}").format(_(status))
	return None


def _previous_step_no(step, steps) -> int | None:
	if cint(step.after_step_no):
		return cint(step.after_step_no)
	earlier = [cint(s.step_no) for s in steps if cint(s.step_no) < cint(step.step_no)]
	return max(earlier) if earlier else None


def evaluate_step(ctx: Context, step, on_date, sent_map, settings, steps=None, status_event=None, visit_event=None):
	"""Evaluate one rule for one AMC cycle (or one PM visit when ctx.visit is set) on `on_date`.

	Returns a frappe._dict with: state (Sent/Due/Pending/Skipped), reason, planned_date, planned_label,
	to, cc, channels (all), due_channels (still to send), last_sent.
	"""
	on_date = getdate(on_date)
	steps = steps or []
	amc, visit = ctx.amc, ctx.visit
	sent = sent_map.get(cint(step.step_no))
	result = frappe._dict(
		state=STATE_PENDING, reason="", planned_date=None, planned_label="", to=[], cc=[], channels=[],
		due_channels=[], last_sent=sent["last"] if sent else None,
	)
	to, cc = resolve_recipients(ctx, step, settings)
	result.to, result.cc = to, cc
	result.channels = expand_channels(step, settings, to, cc)

	if not cint(step.enabled):
		result.state, result.reason = STATE_SKIPPED, _("Rule disabled")
		return result

	mode = step.trigger_mode
	days = cint(step.trigger_days)
	status = amc.cycle_status or "Not started"
	due = getdate(amc.next_due_date) if amc.next_due_date else None

	if mode in VISIT_EVENT_MODES:
		result.planned_label = {
			MODE_VISIT_ASSIGNED: _("When an engineer is assigned"),
			MODE_VISIT_SCHEDULED: _("When an engineer sets the visit date"),
			MODE_VISIT_RESCHEDULED: _("When a visit date changes"),
			MODE_VISIT_REPORTED: _("When a visit report is submitted"),
		}[mode]
		if visit_event == mode and visit:
			if mode == MODE_VISIT_RESCHEDULED:
				# Every reschedule notifies again
				result.due_channels = list(result.channels)
			else:
				result.due_channels = [c for c in result.channels if not (sent and c in sent["channels"])]
			result.planned_date = on_date
			result.state = STATE_DUE if result.due_channels else (STATE_SENT if sent else STATE_SKIPPED)
			result.reason = _("Visit event") if result.due_channels else _("No channel applies")
			return result
		result.state = STATE_SENT if sent else STATE_PENDING
		result.reason = _("Last sent on {0}").format(formatdate(sent["last"])) if sent else _("Waiting for the visit event")
		return result

	if mode == MODE_STATUS:
		result.planned_label = _("When the cycle becomes {0}").format(_(step.on_status or "?"))
		if status_event and status_event == step.on_status:
			planned = on_date
			status = status_event
		else:
			result.state = STATE_SENT if sent else STATE_PENDING
			result.reason = _("Sent on {0}").format(formatdate(sent["last"])) if sent else _("Waiting for the status change")
			return result
	elif mode == MODE_BEFORE_VISIT:
		result.planned_label = _("{0} day(s) before the visit").format(days)
		if not visit or not visit.visit_date:
			result.reason = _("Visit date not set yet")
			if sent:
				result.state = STATE_SENT
			return result
		if visit.status != VISIT_SCHEDULED:
			result.state = STATE_SENT if sent else STATE_SKIPPED
			result.reason = _("Visit is {0}").format(_(visit.status))
			return result
		visit_day = getdate(visit.visit_date)
		planned = add_days(visit_day, -days)
		# A reschedule restarts the reminders that count back from the visit date
		sent = _sent_since(sent, visit.get("last_rescheduled_on"))
		result.last_sent = sent["last"] if sent else None
		if on_date > visit_day and not sent:
			result.planned_date = getdate(planned)
			result.state, result.reason = STATE_SKIPPED, _("Visit date has passed")
			return result
	elif not due:
		result.state, result.reason = STATE_SKIPPED, _("AMC has no Next PM Due Date")
		return result
	elif mode == MODE_BEFORE_DUE:
		planned = add_days(due, -days)
		result.planned_label = _("{0} day(s) before due date").format(days)
	elif mode == MODE_AFTER_DUE:
		planned = add_days(due, days)
		result.planned_label = _("{0} day(s) after due date").format(days)
	elif mode == MODE_AFTER_PREVIOUS:
		previous_no = _previous_step_no(step, steps)
		result.planned_label = _("{0} day(s) after step {1}").format(days, previous_no or "?")
		previous = sent_map.get(cint(previous_no)) if previous_no else None
		if not previous:
			result.reason = _("Waiting for step {0} to be sent").format(previous_no or "?")
			return result
		planned = add_days(previous["first"], days)
	else:
		result.state, result.reason = STATE_SKIPPED, _("Unknown trigger {0}").format(mode)
		return result

	result.planned_date = getdate(planned)
	if mode not in EVENT_MODES and skip_non_working_days():
		direction = -1 if mode in (MODE_BEFORE_DUE, MODE_BEFORE_VISIT) else 1
		shifted = shift_to_working_day(result.planned_date, direction)
		if shifted != result.planned_date:
			result.planned_label += " " + _("(moved to working day)")
			result.planned_date = shifted

	block = _status_block_reason(step, status)
	if block:
		result.state = STATE_SENT if sent else STATE_SKIPPED
		result.reason = block
		return result

	paused_until = amc.get("reminders_paused_until")
	if mode not in EVENT_MODES and paused_until and not cint(step.get("ignore_pause")) and on_date < getdate(paused_until):
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
			_("Repeat due (every {0} days)").format(repeat) if sent else _("Due since {0}").format(formatdate(result.planned_date))
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


def build_context(ctx: Context, step, flow, on_date, status_event=None, extra=None) -> dict:
	on_date = getdate(on_date)
	amc, visit = ctx.amc, ctx.visit
	due = getdate(amc.next_due_date) if amc.next_due_date else on_date
	days_left = date_diff(due, on_date)
	cycles = amc.get("cycles") or []
	visit_day = getdate(visit.visit_date) if visit and visit.visit_date else None
	engineer_names = [frappe.db.get_value("User", e, "full_name") or e for e in ctx.engineers()]
	return {
		"doc": amc,
		"amc": amc,
		"client": ctx.client,
		"visit": visit,
		"step": step,
		"flow": flow,
		"days_left": days_left,
		"days_overdue": max(0, -days_left),
		"due_date": formatdate(due),
		"visit_date": formatdate(visit_day) if visit_day else "",
		"days_to_visit": date_diff(visit_day, on_date) if visit_day else None,
		"amc_url": get_url_to_form("AMC", amc.name),
		"visit_url": get_url_to_form("PM Visit", visit.name) if visit else "",
		"cycle_label": ctx.cycle_label,
		"today": formatdate(on_date),
		"event_status": status_event or "",
		"engineers": ", ".join(engineer_names),
		"last_cycle": cycles[-1] if cycles else None,
		"old_visit_date": "",
		"reschedule_reason": "",
		"reschedule_note": "",
		**(extra or {}),
	}


def render(template: str | None, default: str, context: dict) -> str:
	return frappe.render_template(template or default, context)


def render_step(step, context) -> tuple[str, str]:
	"""Render subject/message in the AMC Settings notification language (English / Arabic / both)."""
	language = get_settings().notification_language or "English"
	visit_rule = step.trigger_mode in VISIT_MODES
	default_subject = tpl.DEFAULT_VISIT_SUBJECT if visit_rule else tpl.DEFAULT_SUBJECT
	default_subject_ar = tpl.DEFAULT_VISIT_SUBJECT_AR if visit_rule else tpl.DEFAULT_SUBJECT_AR

	def english():
		subject = render(step.subject_template, default_subject, context)
		return subject.strip().replace("\n", " "), render(step.message_template, tpl.DEFAULT_MESSAGE, context)

	def arabic():
		previous_lang = frappe.local.lang
		frappe.local.lang = "ar"  # so {{ _(...) }} in the templates renders Arabic
		try:
			subject = render(step.get("subject_template_ar"), default_subject_ar, context)
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
	*, amc=None, client_name=None, visit=None, flow_name=None, step_no=0, step_label, cycle_label, channel, to, cc,
	subject, status, error=None, run_date=None,
):
	log = frappe.new_doc("AMC Notification Log")
	log.update(
		{
			"amc": amc,
			"client_name": client_name,
			"pm_visit": visit,
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


def deliver_channel(channel, *, to, cc, subject, message, ctx: Context, step, settings, indicator="blue"):
	amc, visit = ctx.amc, ctx.visit
	ref_doctype, ref_name = ("PM Visit", visit.name) if visit else ("AMC", amc.name)
	if channel == CH_EMAIL:
		ch.send_email(ch.emails_only(to), ch.emails_only(cc), subject, message, ref_doctype, ref_name)
	elif channel == CH_TEAMS:
		webhook = (step.teams_webhook_url or "").strip() or (settings.default_teams_webhook_url or "").strip()
		facts = [
			(_("Client"), amc.client_name),
			(_("AMC"), f"{amc.amc_title} ({amc.name})"),
			(_("PM due"), formatdate(amc.next_due_date)),
			(_("Cycle status"), _(amc.cycle_status or "")),
		]
		if visit:
			facts += [
				(_("Engineer"), visit.engineer_name or visit.engineer),
				(_("Visit date"), formatdate(visit.visit_date) if visit.visit_date else _("Not set")),
			]
		else:
			facts.append((_("Engineers"), ", ".join(ctx.engineers()) or "-"))
		facts.append((_("Rule"), f"{step.step_no}. {step.step_label}"))
		payload = ch.build_adaptive_card(
			subject,
			ch.html_to_text(message),
			facts,
			url=get_url_to_form(ref_doctype, ref_name),
			color="Attention" if indicator == "red" else "Accent",
		)
		ch.post_to_teams(webhook, payload)
	elif channel == CH_SYSTEM:
		ch.send_system_notification(ch.users_only(to + cc), subject, message, ref_doctype, ref_name, indicator)
	else:
		raise ch.DeliveryError(_("Unknown channel {0}").format(channel))


def send_step(ctx: Context, flow, step, evaluation, on_date, settings, status_event=None, extra_context=None) -> list:
	"""Send every due channel of a rule and record one AMC Notification Log row per channel."""
	context = build_context(ctx, step, flow, on_date, status_event, extra_context)
	indicator = "red" if step.trigger_mode == MODE_AFTER_DUE else "blue"
	to_emails = ch.emails_only(evaluation.to)
	cc_emails = ch.emails_only(evaluation.cc)
	common = {
		"amc": ctx.amc.name,
		"client_name": ctx.amc.client_name,
		"visit": ctx.visit.name if ctx.visit else None,
		"flow_name": flow.name,
		"step_no": step.step_no,
		"step_label": step.step_label,
		"cycle_label": ctx.cycle_label,
		"run_date": on_date,
	}
	logs = []
	try:
		subject, message = render_step(step, context)
	except Exception:
		for channel in evaluation.due_channels:
			logs.append(
				write_log(
					**common, channel=channel, to=to_emails, cc=cc_emails, subject=step.step_label, status="Failed",
					error=_("Template error:\n") + frappe.get_traceback(),
				)
			)
		return logs

	for channel in evaluation.due_channels:
		savepoint = "amc_tracker_send"
		frappe.db.savepoint(savepoint)
		try:
			deliver_channel(
				channel, to=evaluation.to, cc=evaluation.cc, subject=subject, message=message, ctx=ctx, step=step,
				settings=settings, indicator=indicator,
			)
			status, error = "Sent", None
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			status = "Failed"
			error = str(e) if isinstance(e, ch.DeliveryError) else frappe.get_traceback()
		recipients = to_emails if channel != CH_SYSTEM else ch.users_only(evaluation.to + evaluation.cc)
		logs.append(
			write_log(
				**common, channel=channel, to=recipients, cc=cc_emails if channel == CH_EMAIL else [], subject=subject,
				status=status, error=error,
			)
		)
	return logs


def _mark_sent(sent_map, step_no, on_date, logs):
	for log in logs:
		if log.status != "Sent":
			continue
		entry = sent_map.setdefault(cint(step_no), {"first": on_date, "last": on_date, "channels": {}, "sent_on": {}})
		entry["last"] = max(entry["last"], on_date)
		entry["channels"][log.channel] = on_date
		entry["sent_on"][log.channel] = now_datetime()


def _visit_doc(name):
	return frappe.get_doc("PM Visit", name)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def process_amc(amc, on_date=None) -> int:
	"""Evaluate all date-based rules for one AMC (and its visits) and send what is due. Returns logs written."""
	on_date = get_today(on_date)
	flow = get_amc_flow(amc)
	if not flow:
		return 0
	if skip_non_working_days() and not is_working_day(on_date):
		return 0  # nothing is sent on weekends/holidays; the <= checks catch up on the next working day
	settings = get_settings()
	ctx = Context(amc)
	sent_map = get_sent_map(amc.name, flow.name, ctx.cycle_label)
	steps = sorted_steps(flow)
	written = 0
	for step in steps:
		if step.trigger_mode in VISIT_EVENT_MODES:
			continue
		if step.trigger_mode == MODE_STATUS:
			written += _retry_failed_status_step(ctx, flow, step, steps, on_date, sent_map, settings)
			continue
		if step.trigger_mode == MODE_BEFORE_VISIT:
			for v in ctx.visits:
				if v.status != VISIT_SCHEDULED:
					continue
				vctx = Context(amc, _visit_doc(v.name))
				vctx._visits, vctx._client = ctx.visits, ctx.client
				vsent = get_sent_map(amc.name, flow.name, ctx.cycle_label, v.name)
				evaluation = evaluate_step(vctx, step, on_date, vsent, settings, steps)
				if evaluation.state == STATE_DUE:
					written += len(send_step(vctx, flow, step, evaluation, on_date, settings))
			continue
		evaluation = evaluate_step(ctx, step, on_date, sent_map, settings, steps)
		if evaluation.state != STATE_DUE:
			continue
		logs = send_step(ctx, flow, step, evaluation, on_date, settings)
		_mark_sent(sent_map, step.step_no, on_date, logs)
		written += len(logs)
	return written


def _retry_failed_status_step(ctx, flow, step, steps, on_date, sent_map, settings) -> int:
	"""Daily retry of an 'On cycle status change' rule whose channel failed (e.g. no email account yet),
	while the cycle is still in that status and the channel never succeeded this cycle."""
	if not cint(step.enabled) or step.on_status != ctx.amc.cycle_status:
		return 0
	failed = set(
		frappe.get_all(
			"AMC Notification Log",
			filters={
				"amc": ctx.amc.name, "flow": flow.name, "period_label": ctx.cycle_label,
				"step_no": cint(step.step_no), "status": "Failed", "pm_visit": ["is", "not set"],
			},
			pluck="channel",
		)
	)
	if not failed:
		return 0
	evaluation = evaluate_step(ctx, step, on_date, sent_map, settings, steps, status_event=step.on_status)
	evaluation.due_channels = [c for c in evaluation.due_channels if c in failed]
	if evaluation.state != STATE_DUE or not evaluation.due_channels:
		return 0
	logs = send_step(ctx, flow, step, evaluation, on_date, settings, status_event=step.on_status)
	_mark_sent(sent_map, step.step_no, on_date, logs)
	return len(logs)


def fire_status_change(amc, new_status: str, cycle_label: str | None = None) -> int:
	"""Send 'On cycle status change' rules for `new_status`."""
	flow = get_amc_flow(amc)
	if not flow:
		return 0
	on_date = get_today()
	settings = get_settings()
	ctx = Context(amc)
	if cycle_label:
		ctx.cycle_label = cycle_label
	sent_map = get_sent_map(amc.name, flow.name, ctx.cycle_label)
	steps = sorted_steps(flow)
	written = 0
	for step in steps:
		if step.trigger_mode != MODE_STATUS or step.on_status != new_status:
			continue
		evaluation = evaluate_step(ctx, step, on_date, sent_map, settings, steps, status_event=new_status)
		if evaluation.state != STATE_DUE:
			continue
		logs = send_step(ctx, flow, step, evaluation, on_date, settings, status_event=new_status)
		_mark_sent(sent_map, step.step_no, on_date, logs)
		written += len(logs)
	return written


def fire_visit_event(visit, mode: str, extra: dict | None = None) -> int:
	"""Send the rules for a visit event (scheduled / rescheduled / report submitted)."""
	amc = frappe.get_doc("AMC", visit.amc)
	flow = get_amc_flow(amc)
	if not flow:
		return 0
	on_date = get_today()
	settings = get_settings()
	ctx = Context(amc, visit)
	ctx.cycle_label = visit.cycle_label or ctx.cycle_label
	sent_map = get_sent_map(amc.name, flow.name, ctx.cycle_label, visit.name)
	extra_context = {}
	if extra:
		extra_context = {
			"old_visit_date": formatdate(extra.get("old_date")) if extra.get("old_date") else "",
			"reschedule_reason": extra.get("reason") or "",
			"reschedule_note": extra.get("note") or "",
		}
	written = 0
	for step in sorted_steps(flow):
		if step.trigger_mode != mode:
			continue
		evaluation = evaluate_step(ctx, step, on_date, sent_map, settings, visit_event=mode)
		if evaluation.state != STATE_DUE:
			continue
		logs = send_step(ctx, flow, step, evaluation, on_date, settings, extra_context=extra_context)
		_mark_sent(sent_map, step.step_no, on_date, logs)
		written += len(logs)
	return written


# ---------------------------------------------------------------------------
# Dry run ("Test Rules" button) and timeline rendering
# ---------------------------------------------------------------------------

_STATE_COLORS = {STATE_SENT: "green", STATE_DUE: "orange", STATE_PENDING: "blue", STATE_SKIPPED: "gray"}


def _pill(label: str, color: str) -> str:
	return f'<span class="indicator-pill {color}">{escape_html(label)}</span>'


def _people(entries: list[dict]) -> str:
	if not entries:
		return '<span class="text-muted">-</span>'
	return "<br>".join(escape_html(e["email"]) for e in entries)


def evaluate_flow(amc, flow, on_date=None) -> list[dict]:
	on_date = get_today(on_date)
	settings = get_settings()
	ctx = Context(amc)
	sent_map = get_sent_map(amc.name, flow.name, ctx.cycle_label)
	failures = get_failure_map(amc.name, flow.name, ctx.cycle_label)
	steps = sorted_steps(flow)
	rows = []

	def add(step, rctx, evaluation, visit_name=None):
		try:
			subject, _message = render_step(step, build_context(rctx, step, flow, on_date))
		except Exception as e:
			subject = _("Template error: {0}").format(e)
		rows.append(
			{"step": step, "evaluation": evaluation, "subject": subject, "visit": rctx.visit, "failure": failures.get((cint(step.step_no), visit_name))}
		)

	for step in steps:
		if is_visit_step(step):
			visits = [v for v in ctx.visits if step.trigger_mode != MODE_BEFORE_VISIT or v.visit_date]
			if not visits:
				ev = frappe._dict(
					state=STATE_PENDING, reason=_("No PM visits with a date in this cycle yet") if step.trigger_mode == MODE_BEFORE_VISIT else _("Waiting for a visit event"),
					planned_date=None, planned_label=step.trigger_mode, to=[], cc=[], channels=[], due_channels=[], last_sent=None,
				)
				if not cint(step.enabled):
					ev.state, ev.reason = STATE_SKIPPED, _("Rule disabled")
				rows.append({"step": step, "evaluation": ev, "subject": "", "visit": None, "failure": None})
				continue
			for v in visits:
				vctx = Context(amc, _visit_doc(v.name))
				vctx._visits, vctx._client = ctx.visits, ctx.client
				vsent = get_sent_map(amc.name, flow.name, ctx.cycle_label, v.name)
				add(step, vctx, evaluate_step(vctx, step, on_date, vsent, settings, steps), v.name)
			continue
		add(step, ctx, evaluate_step(ctx, step, on_date, sent_map, settings, steps))
	return rows


def render_rows_html(rows, title_html: str, dry_run: bool) -> str:
	head = [_("#"), _("Rule"), _("Visit"), _("Trigger"), _("Planned"), _("To"), _("CC"), _("Channels"), _("Status")]
	if dry_run:
		head.append(_("Subject"))
	html = [title_html, '<div class="table-responsive"><table class="table table-bordered table-sm" style="font-size:12px">']
	html.append("<thead><tr>" + "".join(f"<th>{escape_html(h)}</th>" for h in head) + "</tr></thead><tbody>")
	for row in rows:
		step, ev = row["step"], row["evaluation"]
		state = ev.state
		if dry_run:
			label = _("Would send today") if state == STATE_DUE else _(state)
		else:
			label = _("Pending (sends at next run)") if state == STATE_DUE else _(state)
		status_html = _pill(label, _STATE_COLORS.get(state, "gray"))
		if ev.reason:
			status_html += f'<div class="text-muted small">{escape_html(ev.reason)}</div>'
		if row.get("failure") and state != STATE_SENT:
			status_html += '<div class="small text-danger">{}</div>'.format(
				escape_html(_("Last attempt failed ({0})").format(_(row["failure"].channel)))
			)
		visit = row.get("visit")
		visit_html = (
			f'<a href="/desk/pm-visit/{escape_html(visit.name)}">{escape_html(visit.engineer_name or visit.engineer)}</a>'
			if visit
			else '<span class="text-muted">-</span>'
		)
		channels = ev.due_channels if (dry_run and state == STATE_DUE) else ev.channels
		cells = [
			escape_html(str(step.step_no)),
			escape_html(step.step_label or ""),
			visit_html,
			escape_html(ev.planned_label or _(step.trigger_mode or "")),
			escape_html(formatdate(ev.planned_date)) if ev.planned_date else "-",
			_people(ev.to),
			_people(ev.cc),
			escape_html(", ".join(_(c) for c in channels) or "-"),
			status_html,
		]
		if dry_run:
			cells.append(escape_html(row.get("subject") or ""))
		html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
	html.append("</tbody></table></div>")
	return "".join(html)


@frappe.whitelist()
def dry_run(flow: str, amc: str, on_date: str | None = None) -> dict:
	"""Show which rules of `flow` would fire for `amc` on `on_date`, without sending."""
	frappe.only_for(("System Manager", "AMC Admin"))
	flow_doc = frappe.get_doc("AMC Notification Flow", flow)
	amc_doc = frappe.get_doc("AMC", amc)
	on_date = get_today(on_date)
	rows = evaluate_flow(amc_doc, flow_doc, on_date)
	would_send = [r for r in rows if r["evaluation"].state == STATE_DUE]
	title = (
		"<p><b>{}</b> - {} ({}) - {}: <b>{}</b> - {}: {} - {}: {}</p><p class='text-muted small'>{}</p>"
	).format(
		escape_html(flow_doc.name),
		escape_html(amc_doc.client_name or ""),
		escape_html(amc_doc.name),
		escape_html(_("Cycle")),
		escape_html(cycle_label_of(amc_doc)),
		escape_html(_("Cycle status")),
		escape_html(_(amc_doc.cycle_status or "")),
		escape_html(_("Evaluated as of")),
		escape_html(formatdate(on_date)),
		escape_html(_("Dry run: nothing is sent and nothing is logged. {0} rule(s) would send today.").format(len(would_send))),
	)
	return {
		"html": render_rows_html(rows, title, dry_run=True),
		"would_send": [
			{
				"step_no": r["step"].step_no,
				"step_label": r["step"].step_label,
				"visit": r["visit"].name if r["visit"] else None,
				"to": ch.emails_only(r["evaluation"].to),
				"cc": ch.emails_only(r["evaluation"].cc),
				"channels": r["evaluation"].due_channels,
				"subject": r["subject"],
			}
			for r in would_send
		],
	}


def get_timeline_html(amc) -> str:
	"""HTML for the Notification Timeline on the AMC form."""
	if amc.is_new() or not amc.next_due_date:
		return '<p class="text-muted">{}</p>'.format(
			escape_html(_("Save the AMC with a Next PM Due Date to see its notification timeline."))
		)
	flow = get_amc_flow(amc)
	if not flow:
		return '<p class="text-muted">{}</p>'.format(escape_html(_("No enabled notification rules apply to this AMC.")))
	rows = evaluate_flow(amc, flow)
	title = "<p>{}: <b>{}</b> - {}: <b>{}</b></p>".format(
		escape_html(_("Rules")), escape_html(flow.name), escape_html(_("Cycle")), escape_html(cycle_label_of(amc))
	)
	return render_rows_html(rows, title, dry_run=False)
