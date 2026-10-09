app_name = "hc_tracker"
app_title = "HC Tracker"
app_publisher = "HC Tracker Maintainers"
app_description = "Periodic network health check (HC) tracker with configurable notification flows"
app_email = "admin@example.com"
app_license = "mit"

# Apps
# ------------------

required_apps = []

# Shown on the apps (desktop) screen
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/hc_tracker/images/hc_tracker_logo.svg",
		"title": app_title,
		"route": "/desk/hc-tracker",
		"has_permission": "hc_tracker.permissions.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# Plain (non-bundled) script: listens for real-time "hc_tracker_popup" events and shows the
# on-screen pop-up to the logged-in user. No `bench build` is required for this file.
app_include_js = ["/assets/hc_tracker/js/hc_tracker_popup.js"]

# Installation
# ------------

after_install = "hc_tracker.setup.install.after_install"
after_migrate = "hc_tracker.setup.install.after_migrate"

# Re-apply Asia/Qatar after the setup wizard (the wizard writes its own time zone)
setup_wizard_complete = "hc_tracker.setup.install.after_setup_wizard"

# Permissions
# -----------

permission_query_conditions = {
	"HC Contract": "hc_tracker.permissions.hc_contract_query",
	"HC Notification Log": "hc_tracker.permissions.hc_notification_log_query",
}

has_permission = {
	"HC Contract": "hc_tracker.permissions.hc_contract_has_permission",
	"HC Notification Log": "hc_tracker.permissions.hc_notification_log_has_permission",
}

# Scheduled Tasks
# ---------------
# Cron expressions are evaluated in the site's System Settings time zone (Asia/Qatar).

scheduler_events = {
	"cron": {
		"0 8 * * *": [
			"hc_tracker.notifications.scheduler.run_daily",
		],
	},
}

# Log clearing
# ------------

default_log_clearing_doctypes = {
	"HC Notification Log": 365,
}
