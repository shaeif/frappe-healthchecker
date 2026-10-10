app_name = "amc_tracker"
app_title = "AMC Tracker"
app_publisher = "AMC Tracker Maintainers"
app_description = "AMC tracking: clients, AMCs, preventive maintenance (PM) visits and configurable notifications"
app_email = "admin@example.com"
app_license = "mit"

# Apps
# ------------------

required_apps = []

# Shown on the apps (desktop) screen
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/amc_tracker/images/amc_tracker_logo.svg",
		"title": app_title,
		"route": "/amc-tracker",
		"has_permission": "amc_tracker.permissions.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# Plain (non-bundled) script: listens for real-time "amc_tracker_popup" events and shows the
# on-screen pop-up to the logged-in user. No `bench build` is required for this file.
app_include_js = ["/assets/amc_tracker/js/amc_tracker_popup.js", "/assets/amc_tracker/js/amc_tracker_ui.js"]

# Installation
# ------------

after_install = "amc_tracker.setup.install.after_install"
after_migrate = "amc_tracker.setup.install.after_migrate"

# Re-apply Asia/Qatar after the setup wizard (the wizard writes its own time zone)
setup_wizard_complete = "amc_tracker.setup.install.after_setup_wizard"

# Permissions
# -----------

permission_query_conditions = {
	"Client": "amc_tracker.permissions.client_query",
	"AMC": "amc_tracker.permissions.amc_query",
	"PM Visit": "amc_tracker.permissions.pm_visit_query",
	"Client Contact Log": "amc_tracker.permissions.contact_log_query",
	"AMC Notification Log": "amc_tracker.permissions.notification_log_query",
	"Engineer Leave": "amc_tracker.permissions.engineer_leave_query",
}

has_permission = {
	"Client": "amc_tracker.permissions.client_has_permission",
	"AMC": "amc_tracker.permissions.amc_has_permission",
	"PM Visit": "amc_tracker.permissions.pm_visit_has_permission",
	"Client Contact Log": "amc_tracker.permissions.contact_log_has_permission",
	"AMC Notification Log": "amc_tracker.permissions.notification_log_has_permission",
	"Engineer Leave": "amc_tracker.permissions.engineer_leave_has_permission",
}

# Scheduled Tasks
# ---------------
# Cron expressions are evaluated in the site's System Settings time zone (Asia/Qatar).

scheduler_events = {
	"cron": {
		"0 8 * * *": [
			"amc_tracker.notifications.scheduler.run_daily",
		],
	},
}

# Log clearing
# ------------

default_log_clearing_doctypes = {
	"AMC Notification Log": 365,
}
