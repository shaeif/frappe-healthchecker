"""Default Jinja templates for notification steps.

Available in every subject/message template:
    doc            the HC Contract document
    step           the HC Notification Step row
    flow           the HC Notification Flow document
    days_left      days until next_due_date (negative when overdue)
    days_overdue   days past next_due_date (0 when not overdue)
    due_date       formatted next_due_date
    scheduled_date formatted scheduled_date ("" when not set)
    days_to_scheduled days until scheduled_date (None when not set)
    contract_url   absolute link to the contract form
    cycle_label    current cycle, e.g. 2026-Q4
    today          evaluation date
    event_status   the status that triggered an "On status change" step ("" otherwise)
    last_cycle     latest HC Cycle row (useful for "Signed off" steps), or None
"""

DEFAULT_SUBJECT = "[HC] {{ step.step_label }}: {{ doc.client_name }} ({{ doc.client_id }})"

_FOOTER = """
<table style="border-collapse:collapse;margin-top:12px" cellpadding="4">
<tr><td><b>Client</b></td><td>{{ doc.client_name }} ({{ doc.client_id }})</td></tr>
<tr><td><b>Frequency</b></td><td>{{ doc.frequency }}</td></tr>
<tr><td><b>Cycle</b></td><td>{{ cycle_label }}</td></tr>
<tr><td><b>Due date</b></td><td>{{ due_date }}{% if days_left >= 0 %} (in {{ days_left }} days){% else %} (overdue by {{ days_overdue }} days){% endif %}</td></tr>
<tr><td><b>Scheduled</b></td><td>{{ scheduled_date or "Not booked yet" }}</td></tr>
<tr><td><b>Status</b></td><td>{{ doc.status }}</td></tr>
<tr><td><b>Engineer</b></td><td>{{ doc.engineer_name or doc.assigned_engineer or "-" }}</td></tr>
</table>
<p><a href="{{ contract_url }}">Open contract {{ doc.client_id }} in HC Tracker</a></p>
"""

DEFAULT_MESSAGE = (
	"""<p>Hello,</p>
<p>This is an automatic HC Tracker notification: <b>{{ step.step_label }}</b>.</p>"""
	+ _FOOTER
)

HELPDESK_SUBJECT = "[HC] Book health check: {{ doc.client_name }} due {{ due_date }}"
HELPDESK_MESSAGE = (
	"""<p>Hello Helpdesk,</p>
<p>The {{ doc.frequency | lower }} network health check for <b>{{ doc.client_name }}</b> is due on
<b>{{ due_date }}</b> ({{ days_left }} days from today).</p>
<p><b>Action:</b> contact the client and book the HC window. Then set the contract status to
<b>Scheduled</b> and fill in the <b>Scheduled Date</b>; the assigned engineer is notified automatically.</p>"""
	+ _FOOTER
)

HELPDESK_FOLLOWUP_SUBJECT = "[HC] Reminder - still not booked: {{ doc.client_name }} due {{ due_date }}"
HELPDESK_FOLLOWUP_MESSAGE = (
	"""<p>Hello Helpdesk,</p>
<p>The health check for <b>{{ doc.client_name }}</b> is still <b>{{ doc.status }}</b>.
Please contact the client and book the HC window as soon as possible.</p>"""
	+ _FOOTER
)

ENGINEER_BOOKED_SUBJECT = "[HC] Booked for {{ scheduled_date }}: {{ doc.client_name }}"
ENGINEER_BOOKED_MESSAGE = (
	"""<p>Hello {{ doc.engineer_name or "Engineer" }},</p>
<p>The health check for <b>{{ doc.client_name }}</b> is booked for <b>{{ scheduled_date }}</b>. Please prepare:</p>
<ul>
<li>Confirm remote access / VPN and device credentials</li>
<li>Review the scope and the previous HC report</li>
<li>Prepare the collection scripts for Cisco switches / WLCs, Palo Alto and FortiGate devices</li>
</ul>
<p>Scope: {{ doc.scope or "-" }}</p>"""
	+ _FOOTER
)

ENGINEER_PREP_SUBJECT = "[HC] In {{ days_to_scheduled }} days: {{ doc.client_name }} on {{ scheduled_date }}"
ENGINEER_PREP_MESSAGE = (
	"""<p>Hello {{ doc.engineer_name or "Engineer" }},</p>
<p>Reminder: the health check for <b>{{ doc.client_name }}</b> is scheduled on <b>{{ scheduled_date }}</b>.
Make sure access and credentials are tested before the window.</p>"""
	+ _FOOTER
)

TM_SUBJECT = "[HC] Escalation - not booked, due in {{ days_left }} days: {{ doc.client_name }}"
TM_MESSAGE = (
	"""<p>Hello,</p>
<p>The health check for <b>{{ doc.client_name }}</b> is due on <b>{{ due_date }}</b> ({{ days_left }} days)
and is still <b>{{ doc.status }}</b>. Nobody has booked the HC window yet.</p>
<p><b>Action:</b> follow up with Helpdesk and the engineer so the HC is booked before the due date.</p>"""
	+ _FOOTER
)

OVERDUE_SUBJECT = "[HC] OVERDUE by {{ days_overdue }} days: {{ doc.client_name }} ({{ doc.client_id }})"
OVERDUE_MESSAGE = (
	"""<p>Hello,</p>
<p style="color:#c0392b"><b>The health check for {{ doc.client_name }} is overdue by {{ days_overdue }} days.</b></p>
<p>Current status: <b>{{ doc.status }}</b>. This reminder repeats daily until the HC is signed off.</p>"""
	+ _FOOTER
)

REPORT_SENT_SUBJECT = "[HC] Report ready - get client sign-off: {{ doc.client_name }}"
REPORT_SENT_MESSAGE = (
	"""<p>Hello,</p>
<p>The HC report for <b>{{ doc.client_name }}</b> (cycle {{ cycle_label }}) has been uploaded.</p>
<p><b>Action:</b> send the report to the client and get sign-off. Attach the signed document in
<i>Current Sign-off</i> and set the status to <b>Signed off</b>.</p>
<p>Findings: {{ doc.findings_summary or "-" }}</p>"""
	+ _FOOTER
)
