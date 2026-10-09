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
<li>Prepare the HC checklist for the Cisco switches / WLCs, Palo Alto and FortiGate devices in scope</li>
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

# ---------------------------------------------------------------------------
# v1.3: reschedule + client visit reminder (English)
# ---------------------------------------------------------------------------

RESCHEDULED_SUBJECT = "[HC] Rescheduled to {{ scheduled_date }}: {{ doc.client_name }}"
RESCHEDULED_MESSAGE = (
	"""<p>Hello {{ doc.engineer_name or "Engineer" }},</p>
<p>The health check for <b>{{ doc.client_name }}</b> has been moved
from <b>{{ old_scheduled_date or "-" }}</b> to <b>{{ scheduled_date }}</b>.</p>
<p>Reason: {{ reschedule_reason or "-" }}{% if reschedule_note %} - {{ reschedule_note }}{% endif %}</p>"""
	+ _FOOTER
)

CLIENT_REMINDER_SUBJECT = "Reminder: network health check on {{ scheduled_date }} - {{ doc.client_name }}"
CLIENT_REMINDER_MESSAGE = """<p>Dear {{ doc.client_contact_name or "Customer" }},</p>
<p>This is a friendly reminder that your scheduled network health check is booked for
<b>{{ scheduled_date }}</b>{% if doc.engineer_name %} with our engineer <b>{{ doc.engineer_name }}</b>{% endif %}.</p>
<p>Please make sure remote/on-site access and any required change approvals are in place.
If the date no longer suits you, simply reply to this email and our helpdesk will rebook it.</p>
<p>Kind regards,<br>Network Services Helpdesk</p>"""

# ---------------------------------------------------------------------------
# Arabic defaults (HC Settings > Notification Language = Arabic / English + Arabic)
# ---------------------------------------------------------------------------

_FOOTER_AR = """
<table style="border-collapse:collapse;margin-top:12px" cellpadding="4">
<tr><td><b>العميل</b></td><td>{{ doc.client_name }} ({{ doc.client_id }})</td></tr>
<tr><td><b>التكرار</b></td><td>{{ _(doc.frequency) }}</td></tr>
<tr><td><b>الدورة</b></td><td>{{ cycle_label }}</td></tr>
<tr><td><b>تاريخ الاستحقاق</b></td><td>{{ due_date }}{% if days_left >= 0 %} (بعد {{ days_left }} يوم){% else %} (متأخر {{ days_overdue }} يوم){% endif %}</td></tr>
<tr><td><b>الموعد المحجوز</b></td><td>{{ scheduled_date or "لم يُحجز بعد" }}</td></tr>
<tr><td><b>الحالة</b></td><td>{{ _(doc.status) }}</td></tr>
<tr><td><b>المهندس</b></td><td>{{ doc.engineer_name or doc.assigned_engineer or "-" }}</td></tr>
</table>
<p><a href="{{ contract_url }}">فتح العقد {{ doc.client_id }} في HC Tracker</a></p>
"""

DEFAULT_SUBJECT_AR = "[فحص الشبكة] {{ step.step_label }}: {{ doc.client_name }} ({{ doc.client_id }})"
DEFAULT_MESSAGE_AR = """<p>مرحباً،</p><p>هذا إشعار تلقائي من HC Tracker: <b>{{ step.step_label }}</b>.</p>""" + _FOOTER_AR

HELPDESK_SUBJECT_AR = "[فحص الشبكة] احجز موعد الفحص: {{ doc.client_name }} - الاستحقاق {{ due_date }}"
HELPDESK_MESSAGE_AR = (
	"""<p>مرحباً فريق الدعم،</p>
<p>يستحق فحص صحة الشبكة للعميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ due_date }}</b> (بعد {{ days_left }} يوم).</p>
<p><b>المطلوب:</b> التواصل مع العميل وحجز موعد الفحص، ثم تغيير حالة العقد إلى <b>مجدول</b> وإدخال <b>تاريخ الموعد</b>؛ سيتم إشعار المهندس تلقائياً.</p>"""
	+ _FOOTER_AR
)

HELPDESK_FOLLOWUP_SUBJECT_AR = "[فحص الشبكة] تذكير - لم يُحجز بعد: {{ doc.client_name }} - الاستحقاق {{ due_date }}"
HELPDESK_FOLLOWUP_MESSAGE_AR = (
	"""<p>مرحباً فريق الدعم،</p>
<p>ما زال فحص العميل <b>{{ doc.client_name }}</b> في حالة <b>{{ _(doc.status) }}</b>. يرجى التواصل مع العميل وحجز الموعد في أقرب وقت.</p>"""
	+ _FOOTER_AR
)

ENGINEER_BOOKED_SUBJECT_AR = "[فحص الشبكة] تم الحجز بتاريخ {{ scheduled_date }}: {{ doc.client_name }}"
ENGINEER_BOOKED_MESSAGE_AR = (
	"""<p>مرحباً {{ doc.engineer_name or "المهندس" }}،</p>
<p>تم حجز فحص صحة الشبكة للعميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ scheduled_date }}</b>. يرجى التحضير:</p>
<ul><li>التأكد من الوصول عن بُعد / VPN وبيانات الدخول للأجهزة</li>
<li>مراجعة نطاق العمل وتقرير الفحص السابق</li>
<li>تجهيز قائمة الفحص لأجهزة Cisco و Palo Alto و FortiGate ضمن النطاق</li></ul>
<p>النطاق: {{ doc.scope or "-" }}</p>"""
	+ _FOOTER_AR
)

ENGINEER_PREP_SUBJECT_AR = "[فحص الشبكة] بعد {{ days_to_scheduled }} يوم: {{ doc.client_name }} بتاريخ {{ scheduled_date }}"
ENGINEER_PREP_MESSAGE_AR = (
	"""<p>مرحباً {{ doc.engineer_name or "المهندس" }}،</p>
<p>تذكير: فحص العميل <b>{{ doc.client_name }}</b> محجوز بتاريخ <b>{{ scheduled_date }}</b>. تأكد من اختبار الوصول وبيانات الدخول قبل الموعد.</p>"""
	+ _FOOTER_AR
)

TM_SUBJECT_AR = "[فحص الشبكة] تصعيد - لم يُحجز والاستحقاق بعد {{ days_left }} يوم: {{ doc.client_name }}"
TM_MESSAGE_AR = (
	"""<p>مرحباً،</p>
<p>يستحق فحص العميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ due_date }}</b> ({{ days_left }} يوم) وما زال في حالة <b>{{ _(doc.status) }}</b>، ولم يتم حجز موعد حتى الآن.</p>
<p><b>المطلوب:</b> المتابعة مع فريق الدعم والمهندس لحجز الموعد قبل تاريخ الاستحقاق.</p>"""
	+ _FOOTER_AR
)

OVERDUE_SUBJECT_AR = "[فحص الشبكة] متأخر {{ days_overdue }} يوم: {{ doc.client_name }} ({{ doc.client_id }})"
OVERDUE_MESSAGE_AR = (
	"""<p>مرحباً،</p>
<p style="color:#c0392b"><b>فحص صحة الشبكة للعميل {{ doc.client_name }} متأخر {{ days_overdue }} يوم.</b></p>
<p>الحالة الحالية: <b>{{ _(doc.status) }}</b>. سيتكرر هذا التذكير يومياً حتى اعتماد الفحص.</p>"""
	+ _FOOTER_AR
)

REPORT_SENT_SUBJECT_AR = "[فحص الشبكة] التقرير جاهز - احصل على اعتماد العميل: {{ doc.client_name }}"
REPORT_SENT_MESSAGE_AR = (
	"""<p>مرحباً،</p>
<p>تم رفع تقرير الفحص للعميل <b>{{ doc.client_name }}</b> (الدورة {{ cycle_label }}).</p>
<p><b>المطلوب:</b> إرسال التقرير إلى العميل والحصول على الاعتماد، ثم إرفاق المستند المعتمد وتغيير الحالة إلى <b>معتمد</b>.</p>
<p>الملاحظات: {{ doc.findings_summary or "-" }}</p>"""
	+ _FOOTER_AR
)

RESCHEDULED_SUBJECT_AR = "[فحص الشبكة] تغيير الموعد إلى {{ scheduled_date }}: {{ doc.client_name }}"
RESCHEDULED_MESSAGE_AR = (
	"""<p>مرحباً {{ doc.engineer_name or "المهندس" }}،</p>
<p>تم تغيير موعد فحص العميل <b>{{ doc.client_name }}</b> من <b>{{ old_scheduled_date or "-" }}</b> إلى <b>{{ scheduled_date }}</b>.</p>
<p>السبب: {{ _(reschedule_reason) if reschedule_reason else "-" }}{% if reschedule_note %} - {{ reschedule_note }}{% endif %}</p>"""
	+ _FOOTER_AR
)

CLIENT_REMINDER_SUBJECT_AR = "تذكير: فحص صحة الشبكة بتاريخ {{ scheduled_date }} - {{ doc.client_name }}"
CLIENT_REMINDER_MESSAGE_AR = """<p>عزيزنا {{ doc.client_contact_name or "العميل" }}،</p>
<p>نود تذكيركم بأن موعد فحص صحة الشبكة محجوز بتاريخ <b>{{ scheduled_date }}</b>{% if doc.engineer_name %} مع مهندسنا <b>{{ doc.engineer_name }}</b>{% endif %}.</p>
<p>يرجى التأكد من توفر صلاحيات الوصول عن بُعد أو في الموقع وأي موافقات تغيير مطلوبة. إذا لم يعد الموعد مناسباً، يرجى الرد على هذا البريد وسيقوم فريق الدعم بإعادة الحجز.</p>
<p>مع خالص التحية،<br>فريق دعم خدمات الشبكات</p>"""

# Booking request email to the client (HC Settings can override)
BOOKING_REQUEST_SUBJECT = "Network health check booking - {{ doc.client_name }} (due {{ due_date }})"
BOOKING_REQUEST_MESSAGE = """<p>Dear {{ doc.client_contact_name or "Customer" }},</p>
<p>Your {{ doc.frequency | lower }} network health check is due on <b>{{ due_date }}</b>.
{% if proposed_dates %}Please let us know which of the following dates suits you (or propose another date):{% else %}Please propose a date that suits you.{% endif %}</p>
{% if proposed_dates %}<ul>{% for d in proposed_dates %}<li>{{ d }}</li>{% endfor %}</ul>{% endif %}
<p>Scope: {{ doc.scope or "as per contract" }}</p>
<p>Simply reply to this email with your preferred date and time window.</p>
<p>Kind regards,<br>{{ sender_name }}<br>Network Services Helpdesk</p>"""

BOOKING_REQUEST_SUBJECT_AR = "حجز موعد فحص صحة الشبكة - {{ doc.client_name }} (الاستحقاق {{ due_date }})"
BOOKING_REQUEST_MESSAGE_AR = """<p>عزيزنا {{ doc.client_contact_name or "العميل" }}،</p>
<p>يستحق فحص صحة الشبكة بتاريخ <b>{{ due_date }}</b>. يرجى إفادتنا بالموعد المناسب لكم{% if proposed_dates %} من التواريخ التالية:{% else %}.{% endif %}</p>
{% if proposed_dates %}<ul>{% for d in proposed_dates %}<li>{{ d }}</li>{% endfor %}</ul>{% endif %}
<p>يرجى الرد على هذا البريد بالتاريخ والوقت المناسبين.</p>
<p>مع خالص التحية،<br>{{ sender_name }}<br>فريق دعم خدمات الشبكات</p>"""


def rtl(html: str) -> str:
	return f'<div dir="rtl" lang="ar" style="text-align:right">{html}</div>'


def bilingual(html_en: str, html_ar: str) -> str:
	return f'{html_en}<hr style="margin:18px 0">{rtl(html_ar)}'


def pick(en: str, ar: str) -> str:
	"""Short system texts (digest/to-do/summary) in the configured notification language."""
	import frappe

	language = frappe.get_cached_doc("HC Settings").notification_language or "English"
	if language == "Arabic":
		return ar
	if language == "English + Arabic":
		return f"{en} | {ar}"
	return en


def wrap(html: str) -> str:
	"""Wrap a system email body for the configured language (adds RTL for Arabic)."""
	import frappe

	language = frappe.get_cached_doc("HC Settings").notification_language or "English"
	return rtl(html) if language == "Arabic" else html
