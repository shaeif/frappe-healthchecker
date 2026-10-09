"""Default Jinja templates for notification rules.

Available in every subject/message template:
    doc / amc        the AMC document
    client           the client (client_name, contact_name, contact_email, contact_phone, cc_emails)
    visit            the PM Visit for visit rules, else None
    step, flow       the rule row and its rule set
    days_left        days until the Next PM Due Date (negative when overdue)
    days_overdue     days past the due date (0 when not overdue)
    due_date         formatted Next PM Due Date
    visit_date       formatted visit date ("" when not set)
    days_to_visit    days until the visit date (None when not set)
    amc_url          link to the AMC form
    visit_url        link to the PM Visit form ("" for AMC rules)
    cycle_label      current PM cycle, e.g. 2026-Q4
    engineers        engineer names of the current cycle
    today            evaluation date
    event_status     the cycle status that triggered an "On cycle status change" rule
    old_visit_date, reschedule_reason, reschedule_note   for "On visit rescheduled" rules
    last_cycle       latest PM Cycle history row, or None
"""

# ---------------------------------------------------------------------------
# English
# ---------------------------------------------------------------------------

DEFAULT_SUBJECT = "[AMC] {{ step.step_label }}: {{ doc.client_name }} - {{ doc.amc_title }}"
DEFAULT_VISIT_SUBJECT = "[AMC] {{ step.step_label }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"

_FOOTER = """
<table style="border-collapse:collapse;margin-top:12px;font-size:13px" cellpadding="4">
<tr><td><b>Client</b></td><td>{{ doc.client_name }}</td></tr>
<tr><td><b>AMC</b></td><td>{{ doc.amc_title }} ({{ doc.name }})</td></tr>
<tr><td><b>PM frequency</b></td><td>{{ doc.frequency }}</td></tr>
<tr><td><b>Cycle</b></td><td>{{ cycle_label }}</td></tr>
<tr><td><b>PM due</b></td><td>{{ due_date }}{% if days_left >= 0 %} (in {{ days_left }} days){% else %} (overdue by {{ days_overdue }} days){% endif %}</td></tr>
<tr><td><b>Cycle status</b></td><td>{{ doc.cycle_status }}</td></tr>
<tr><td><b>Engineers</b></td><td>{{ engineers or "Not assigned yet" }}</td></tr>
{% if visit %}<tr><td><b>Visit</b></td><td>{{ visit.engineer_name or visit.engineer }} - {{ visit_date or "date not set" }}{% if visit.visit_mode %} ({{ visit.visit_mode }}){% endif %}</td></tr>{% endif %}
</table>
<p><a href="{{ amc_url }}">Open AMC {{ doc.name }}</a>{% if visit %} &middot; <a href="{{ visit_url }}">Open PM visit {{ visit.name }}</a>{% endif %}</p>
"""

DEFAULT_MESSAGE = """<p>Hello,</p>
<p>This is an automatic AMC Tracker notification: <b>{{ step.step_label }}</b>.</p>""" + _FOOTER

ASSIGN_SUBJECT = "[AMC] Assign engineers: {{ doc.client_name }} PM due {{ due_date }}"
ASSIGN_MESSAGE = """<p>Hello Helpdesk,</p>
<p>The {{ doc.frequency | lower }} preventive maintenance for <b>{{ doc.client_name }}</b> ({{ doc.amc_title }}) is due on
<b>{{ due_date }}</b> ({{ days_left }} days from today).</p>
<p><b>Action:</b> open the AMC and click <b>Assign Engineers</b>. Each engineer then agrees the visit date with the client.</p>""" + _FOOTER

PLEASE_SCHEDULE_SUBJECT = "[AMC] Please schedule your PM visit: {{ doc.client_name }} (due {{ due_date }})"
PLEASE_SCHEDULE_MESSAGE = """<p>Hello,</p>
<p>You have been assigned to the preventive maintenance of <b>{{ doc.client_name }}</b> ({{ doc.amc_title }}), due on
<b>{{ due_date }}</b>.</p>
<p><b>Action:</b> agree a date with the client and set it on your PM visit (on-site or remote).</p>
<p>Scope: {{ doc.scope or "-" }}</p>""" + _FOOTER

SCHEDULE_REMINDER_SUBJECT = "[AMC] Reminder - PM visit date not set: {{ doc.client_name }} (due {{ due_date }})"
SCHEDULE_REMINDER_MESSAGE = """<p>Hello,</p>
<p>The PM visit for <b>{{ doc.client_name }}</b> still has no date. The PM is due on <b>{{ due_date }}</b>
({{ days_left }} days).</p>
<p><b>Action:</b> agree the date with the client and set it on your PM visit.</p>""" + _FOOTER

VISIT_SCHEDULED_SUBJECT = "[AMC] Visit scheduled {{ visit_date }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"
VISIT_SCHEDULED_MESSAGE = """<p>Hello,</p>
<p><b>{{ visit.engineer_name or visit.engineer }}</b> scheduled the PM visit for <b>{{ doc.client_name }}</b> on
<b>{{ visit_date }}</b>{% if visit.visit_mode %} ({{ visit.visit_mode }}){% endif %}.</p>""" + _FOOTER

VISIT_PREP_SUBJECT = "[AMC] In {{ days_to_visit }} days: PM visit {{ doc.client_name }} on {{ visit_date }}"
VISIT_PREP_MESSAGE = """<p>Hello {{ visit.engineer_name or "Engineer" }},</p>
<p>Reminder: your PM visit for <b>{{ doc.client_name }}</b> is on <b>{{ visit_date }}</b>{% if visit.visit_mode %} ({{ visit.visit_mode }}){% endif %}.</p>
<ul>
<li>Confirm remote access / site access and credentials</li>
<li>Review the scope and the previous PM report</li>
<li>Prepare the checklist for the devices in scope</li>
</ul>
<p>Scope: {{ doc.scope or "-" }}</p>""" + _FOOTER

CLIENT_REMINDER_SUBJECT = "Reminder: preventive maintenance visit on {{ visit_date }} - {{ doc.client_name }}"
CLIENT_REMINDER_MESSAGE = """<p>Dear {{ client.contact_name or "Customer" }},</p>
<p>This is a friendly reminder that your scheduled preventive maintenance is planned for <b>{{ visit_date }}</b>
{% if visit.visit_mode == "Remote" %}(remote session){% else %}(on-site){% endif %} with our engineer
<b>{{ visit.engineer_name or visit.engineer }}</b>.</p>
<p>Please make sure access and any required change approvals are in place.
If the date no longer suits you, simply reply to this email.</p>
<p>Kind regards,<br>Network Services Team</p>"""

CLIENT_CONFIRMATION_SUBJECT = "Preventive maintenance visit confirmed for {{ visit_date }} - {{ doc.client_name }}"
CLIENT_CONFIRMATION_MESSAGE = """<p>Dear {{ client.contact_name or "Customer" }},</p>
<p>We confirm your preventive maintenance visit on <b>{{ visit_date }}</b>
{% if visit.visit_mode == "Remote" %}(remote session){% else %}(on-site){% endif %} with our engineer
<b>{{ visit.engineer_name or visit.engineer }}</b>.</p>
<p>Kind regards,<br>Network Services Team</p>"""

TM_SUBJECT = "[AMC] Escalation - PM not scheduled, due in {{ days_left }} days: {{ doc.client_name }}"
TM_MESSAGE = """<p>Hello,</p>
<p>The preventive maintenance for <b>{{ doc.client_name }}</b> is due on <b>{{ due_date }}</b> ({{ days_left }} days)
and is still <b>{{ doc.cycle_status }}</b>.</p>
<p><b>Action:</b> follow up with the helpdesk and the engineers so every visit is scheduled before the due date.</p>""" + _FOOTER

OVERDUE_SUBJECT = "[AMC] PM OVERDUE by {{ days_overdue }} days: {{ doc.client_name }} - {{ doc.amc_title }}"
OVERDUE_MESSAGE = """<p>Hello,</p>
<p style="color:#c0392b"><b>The preventive maintenance for {{ doc.client_name }} is overdue by {{ days_overdue }} days.</b></p>
<p>Cycle status: <b>{{ doc.cycle_status }}</b>. This reminder repeats daily until the cycle is signed off.</p>""" + _FOOTER

RESCHEDULED_SUBJECT = "[AMC] Visit moved to {{ visit_date }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"
RESCHEDULED_MESSAGE = """<p>Hello,</p>
<p>The PM visit of <b>{{ visit.engineer_name or visit.engineer }}</b> for <b>{{ doc.client_name }}</b> has been moved
from <b>{{ old_visit_date or "-" }}</b> to <b>{{ visit_date }}</b>.</p>
<p>Reason: {{ reschedule_reason or "-" }}{% if reschedule_note %} - {{ reschedule_note }}{% endif %}</p>""" + _FOOTER

REPORTS_READY_SUBJECT = "[AMC] PM reports ready - sign-off needed: {{ doc.client_name }} ({{ cycle_label }})"
REPORTS_READY_MESSAGE = """<p>Hello,</p>
<p>All PM visit reports for <b>{{ doc.client_name }}</b> (cycle {{ cycle_label }}) have been submitted.</p>
<p><b>Action:</b> share the report(s) with the client, attach the client sign-off on the AMC and click
<b>Sign Off Cycle</b>.</p>
<p>Findings: {{ doc.findings_summary or "-" }}</p>""" + _FOOTER

# Client scheduling email (sent from the AMC or the PM Visit form; AMC Settings can override)
SCHEDULING_EMAIL_SUBJECT = "Preventive maintenance scheduling - {{ doc.client_name }} (due {{ due_date }})"
SCHEDULING_EMAIL_MESSAGE = """<p>Dear {{ client.contact_name or "Customer" }},</p>
<p>Your {{ doc.frequency | lower }} preventive maintenance is due on <b>{{ due_date }}</b>.
{% if proposed_dates %}Please let us know which of the following dates suits you (or propose another date):{% else %}Please propose a date that suits you.{% endif %}</p>
{% if proposed_dates %}<ul>{% for d in proposed_dates %}<li>{{ d }}</li>{% endfor %}</ul>{% endif %}
{% if visit %}<p>Engineer: {{ visit.engineer_name or visit.engineer }}{% if visit.visit_mode %} ({{ visit.visit_mode }}){% endif %}</p>{% endif %}
<p>Scope: {{ doc.scope or "as per contract" }}</p>
<p>Simply reply to this email with your preferred date and time window.</p>
<p>Kind regards,<br>{{ sender_name }}<br>Network Services Team</p>"""

# ---------------------------------------------------------------------------
# Arabic (AMC Settings > Notification Language = Arabic / English + Arabic)
# ---------------------------------------------------------------------------

DEFAULT_SUBJECT_AR = "[عقد الصيانة] {{ step.step_label }}: {{ doc.client_name }} - {{ doc.amc_title }}"
DEFAULT_VISIT_SUBJECT_AR = "[عقد الصيانة] {{ step.step_label }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"

_FOOTER_AR = """
<table style="border-collapse:collapse;margin-top:12px;font-size:13px" cellpadding="4">
<tr><td><b>العميل</b></td><td>{{ doc.client_name }}</td></tr>
<tr><td><b>العقد</b></td><td>{{ doc.amc_title }} ({{ doc.name }})</td></tr>
<tr><td><b>تكرار الصيانة</b></td><td>{{ _(doc.frequency) }}</td></tr>
<tr><td><b>الدورة</b></td><td>{{ cycle_label }}</td></tr>
<tr><td><b>موعد الاستحقاق</b></td><td>{{ due_date }}{% if days_left >= 0 %} (بعد {{ days_left }} يوم){% else %} (متأخر {{ days_overdue }} يوم){% endif %}</td></tr>
<tr><td><b>حالة الدورة</b></td><td>{{ _(doc.cycle_status) }}</td></tr>
<tr><td><b>المهندسون</b></td><td>{{ engineers or "لم يُعيَّنوا بعد" }}</td></tr>
{% if visit %}<tr><td><b>الزيارة</b></td><td>{{ visit.engineer_name or visit.engineer }} - {{ visit_date or "لم يُحدد الموعد" }}{% if visit.visit_mode %} ({{ _(visit.visit_mode) }}){% endif %}</td></tr>{% endif %}
</table>
<p><a href="{{ amc_url }}">فتح العقد {{ doc.name }}</a>{% if visit %} &middot; <a href="{{ visit_url }}">فتح زيارة الصيانة {{ visit.name }}</a>{% endif %}</p>
"""

DEFAULT_MESSAGE_AR = """<p>مرحباً،</p><p>هذا إشعار تلقائي من نظام متابعة عقود الصيانة: <b>{{ step.step_label }}</b>.</p>""" + _FOOTER_AR

ASSIGN_SUBJECT_AR = "[عقد الصيانة] تعيين المهندسين: {{ doc.client_name }} - الاستحقاق {{ due_date }}"
ASSIGN_MESSAGE_AR = """<p>مرحباً فريق الدعم،</p>
<p>تستحق الصيانة الوقائية للعميل <b>{{ doc.client_name }}</b> ({{ doc.amc_title }}) بتاريخ <b>{{ due_date }}</b> (بعد {{ days_left }} يوم).</p>
<p><b>المطلوب:</b> فتح العقد والضغط على <b>تعيين المهندسين</b>، ثم يتفق كل مهندس مع العميل على موعد الزيارة.</p>""" + _FOOTER_AR

PLEASE_SCHEDULE_SUBJECT_AR = "[عقد الصيانة] يرجى تحديد موعد زيارة الصيانة: {{ doc.client_name }} (الاستحقاق {{ due_date }})"
PLEASE_SCHEDULE_MESSAGE_AR = """<p>مرحباً،</p>
<p>تم تعيينك للصيانة الوقائية للعميل <b>{{ doc.client_name }}</b> ({{ doc.amc_title }}) المستحقة بتاريخ <b>{{ due_date }}</b>.</p>
<p><b>المطلوب:</b> الاتفاق مع العميل على موعد وإدخاله في زيارة الصيانة (في الموقع أو عن بُعد).</p>
<p>النطاق: {{ doc.scope or "-" }}</p>""" + _FOOTER_AR

SCHEDULE_REMINDER_SUBJECT_AR = "[عقد الصيانة] تذكير - لم يُحدد موعد الزيارة: {{ doc.client_name }} (الاستحقاق {{ due_date }})"
SCHEDULE_REMINDER_MESSAGE_AR = """<p>مرحباً،</p>
<p>ما زالت زيارة الصيانة للعميل <b>{{ doc.client_name }}</b> بدون موعد، والصيانة مستحقة بتاريخ <b>{{ due_date }}</b> (بعد {{ days_left }} يوم).</p>
<p><b>المطلوب:</b> الاتفاق على الموعد مع العميل وإدخاله في زيارة الصيانة.</p>""" + _FOOTER_AR

VISIT_SCHEDULED_SUBJECT_AR = "[عقد الصيانة] تم تحديد الزيارة {{ visit_date }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"
VISIT_SCHEDULED_MESSAGE_AR = """<p>مرحباً،</p>
<p>حدد المهندس <b>{{ visit.engineer_name or visit.engineer }}</b> موعد زيارة الصيانة للعميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ visit_date }}</b>{% if visit.visit_mode %} ({{ _(visit.visit_mode) }}){% endif %}.</p>""" + _FOOTER_AR

VISIT_PREP_SUBJECT_AR = "[عقد الصيانة] بعد {{ days_to_visit }} يوم: زيارة {{ doc.client_name }} بتاريخ {{ visit_date }}"
VISIT_PREP_MESSAGE_AR = """<p>مرحباً {{ visit.engineer_name or "المهندس" }}،</p>
<p>تذكير: زيارة الصيانة للعميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ visit_date }}</b>{% if visit.visit_mode %} ({{ _(visit.visit_mode) }}){% endif %}.</p>
<ul><li>التأكد من صلاحيات الوصول وبيانات الدخول</li><li>مراجعة النطاق وتقرير الصيانة السابق</li><li>تجهيز قائمة الفحص للأجهزة ضمن النطاق</li></ul>
<p>النطاق: {{ doc.scope or "-" }}</p>""" + _FOOTER_AR

CLIENT_REMINDER_SUBJECT_AR = "تذكير: زيارة الصيانة الوقائية بتاريخ {{ visit_date }} - {{ doc.client_name }}"
CLIENT_REMINDER_MESSAGE_AR = """<p>عزيزنا {{ client.contact_name or "العميل" }}،</p>
<p>نود تذكيركم بأن موعد الصيانة الوقائية بتاريخ <b>{{ visit_date }}</b> {% if visit.visit_mode == "Remote" %}(جلسة عن بُعد){% else %}(في الموقع){% endif %} مع مهندسنا <b>{{ visit.engineer_name or visit.engineer }}</b>.</p>
<p>يرجى التأكد من توفر صلاحيات الوصول وأي موافقات تغيير مطلوبة. إذا لم يعد الموعد مناسباً، يرجى الرد على هذا البريد.</p>
<p>مع خالص التحية،<br>فريق خدمات الشبكات</p>"""

CLIENT_CONFIRMATION_SUBJECT_AR = "تأكيد موعد زيارة الصيانة الوقائية {{ visit_date }} - {{ doc.client_name }}"
CLIENT_CONFIRMATION_MESSAGE_AR = """<p>عزيزنا {{ client.contact_name or "العميل" }}،</p>
<p>نؤكد موعد زيارة الصيانة الوقائية بتاريخ <b>{{ visit_date }}</b> {% if visit.visit_mode == "Remote" %}(جلسة عن بُعد){% else %}(في الموقع){% endif %} مع مهندسنا <b>{{ visit.engineer_name or visit.engineer }}</b>.</p>
<p>مع خالص التحية،<br>فريق خدمات الشبكات</p>"""

TM_SUBJECT_AR = "[عقد الصيانة] تصعيد - لم تُجدول الصيانة والاستحقاق بعد {{ days_left }} يوم: {{ doc.client_name }}"
TM_MESSAGE_AR = """<p>مرحباً،</p>
<p>تستحق الصيانة الوقائية للعميل <b>{{ doc.client_name }}</b> بتاريخ <b>{{ due_date }}</b> ({{ days_left }} يوم) وما زالت في حالة <b>{{ _(doc.cycle_status) }}</b>.</p>
<p><b>المطلوب:</b> المتابعة مع فريق الدعم والمهندسين لجدولة جميع الزيارات قبل تاريخ الاستحقاق.</p>""" + _FOOTER_AR

OVERDUE_SUBJECT_AR = "[عقد الصيانة] الصيانة متأخرة {{ days_overdue }} يوم: {{ doc.client_name }} - {{ doc.amc_title }}"
OVERDUE_MESSAGE_AR = """<p>مرحباً،</p>
<p style="color:#c0392b"><b>الصيانة الوقائية للعميل {{ doc.client_name }} متأخرة {{ days_overdue }} يوم.</b></p>
<p>حالة الدورة: <b>{{ _(doc.cycle_status) }}</b>. سيتكرر هذا التذكير يومياً حتى اعتماد الدورة.</p>""" + _FOOTER_AR

RESCHEDULED_SUBJECT_AR = "[عقد الصيانة] تغيير موعد الزيارة إلى {{ visit_date }}: {{ doc.client_name }} - {{ visit.engineer_name or visit.engineer }}"
RESCHEDULED_MESSAGE_AR = """<p>مرحباً،</p>
<p>تم تغيير موعد زيارة الصيانة للمهندس <b>{{ visit.engineer_name or visit.engineer }}</b> لدى العميل <b>{{ doc.client_name }}</b> من <b>{{ old_visit_date or "-" }}</b> إلى <b>{{ visit_date }}</b>.</p>
<p>السبب: {{ _(reschedule_reason) if reschedule_reason else "-" }}{% if reschedule_note %} - {{ reschedule_note }}{% endif %}</p>""" + _FOOTER_AR

REPORTS_READY_SUBJECT_AR = "[عقد الصيانة] تقارير الصيانة جاهزة - مطلوب الاعتماد: {{ doc.client_name }} ({{ cycle_label }})"
REPORTS_READY_MESSAGE_AR = """<p>مرحباً،</p>
<p>تم تقديم جميع تقارير زيارات الصيانة للعميل <b>{{ doc.client_name }}</b> (الدورة {{ cycle_label }}).</p>
<p><b>المطلوب:</b> مشاركة التقارير مع العميل، وإرفاق اعتماد العميل في العقد، ثم الضغط على <b>اعتماد الدورة</b>.</p>
<p>الملاحظات: {{ doc.findings_summary or "-" }}</p>""" + _FOOTER_AR

SCHEDULING_EMAIL_SUBJECT_AR = "جدولة الصيانة الوقائية - {{ doc.client_name }} (الاستحقاق {{ due_date }})"
SCHEDULING_EMAIL_MESSAGE_AR = """<p>عزيزنا {{ client.contact_name or "العميل" }}،</p>
<p>تستحق الصيانة الوقائية بتاريخ <b>{{ due_date }}</b>. يرجى إفادتنا بالموعد المناسب لكم{% if proposed_dates %} من التواريخ التالية:{% else %}.{% endif %}</p>
{% if proposed_dates %}<ul>{% for d in proposed_dates %}<li>{{ d }}</li>{% endfor %}</ul>{% endif %}
{% if visit %}<p>المهندس: {{ visit.engineer_name or visit.engineer }}</p>{% endif %}
<p>يرجى الرد على هذا البريد بالتاريخ والوقت المناسبين.</p>
<p>مع خالص التحية،<br>{{ sender_name }}<br>فريق خدمات الشبكات</p>"""


def rtl(html: str) -> str:
	return f'<div dir="rtl" lang="ar" style="text-align:right">{html}</div>'


def bilingual(html_en: str, html_ar: str) -> str:
	return f'{html_en}<hr style="margin:18px 0">{rtl(html_ar)}'


def _language() -> str:
	import frappe

	return frappe.get_cached_doc("AMC Settings").notification_language or "English"


def pick(en: str, ar: str) -> str:
	"""Short system texts (digest / to-do / summary) in the configured notification language."""
	language = _language()
	if language == "Arabic":
		return ar
	if language == "English + Arabic":
		return f"{en} | {ar}"
	return en


def wrap(html: str) -> str:
	"""Wrap a system email body for the configured language (adds RTL for Arabic)."""
	return rtl(html) if _language() == "Arabic" else html
