#!/usr/bin/env bash
# One-command install: .env -> image build -> stack up -> site created -> setup wizard skipped.
#
# Usage:
#   ./scripts/install.sh                                   # local test on http://amc.localhost:8080
#   ./scripts/install.sh --site amc.example.com --url https://amc.example.com --port 80
#   ./scripts/install.sh --demo                            # also create the test-plan users, clients and AMCs
#
# Options:
#   --site NAME    SITE_NAME (hostname users type in the browser)   [only used when .env is created]
#   --url URL      HOST_NAME (base URL in email / Teams links)      [only used when .env is created]
#   --port N       HTTP_PORT published on the host                  [only used when .env is created]
#   --demo         sample users (one per role) and clients and AMCs T-001..T-006 from docs/TEST_PLAN.md
#   --no-build     use the existing ${CUSTOM_IMAGE}:${CUSTOM_TAG} image instead of building it
#
# Safe to run again: an existing .env and an existing site are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

site="" url="" port="" demo=0 build=1
while [[ $# -gt 0 ]]; do
	case "$1" in
		--site) site="$2"; shift 2 ;;
		--url) url="$2"; shift 2 ;;
		--port) port="$2"; shift 2 ;;
		--demo) demo=1; shift ;;
		--no-build) build=0; shift ;;
		-h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
	esac
done

step() { printf '\n==> %s\n' "$*"; }
random_password() { openssl rand -base64 24 2>/dev/null | tr -d '/+=' | cut -c1-24 || head -c 256 /dev/urandom | tr -dc 'A-Za-z0-9' | cut -c1-24; }
set_env() { # set_env KEY VALUE (in .env)
	local tmp; tmp=$(mktemp)
	awk -v k="$1" -v v="$2" 'BEGIN { FS = OFS = "=" } $1 == k { print k, v; next } { print }' .env > "$tmp"
	cat "$tmp" > .env && rm -f "$tmp"
}

command -v docker >/dev/null || { echo "Docker is not installed." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "The Docker Compose v2 plugin is missing (docker compose ...)." >&2; exit 1; }

# 1. .env
if [[ ! -f .env ]]; then
	step "Creating .env with generated passwords"
	cp .env.example .env
	chmod 600 .env
	set_env DB_ROOT_PASSWORD "$(random_password)"
	set_env ADMIN_PASSWORD "$(random_password)"
	[[ -n "$port" ]] && set_env HTTP_PORT "$port"
	if [[ -n "$site" ]]; then
		set_env SITE_NAME "$site"
		[[ -z "$url" ]] && url="http://$site:${port:-8080}"
	fi
	[[ -z "$url" && -n "$port" ]] && url="http://amc.localhost:$port"
	[[ -n "$url" ]] && set_env HOST_NAME "${url%/}"
else
	step "Using the existing .env"
	[[ -n "$site$url$port" ]] && echo "    (--site/--url/--port are ignored: edit .env to change them)"
fi
set -a; source .env; set +a
if grep -q 'change-me' <<<"$DB_ROOT_PASSWORD$ADMIN_PASSWORD"; then
	echo "Set real DB_ROOT_PASSWORD and ADMIN_PASSWORD in .env first (or delete .env to generate them)." >&2
	exit 1
fi

# 2. Image
if (( build )); then
	step "Building ${CUSTOM_IMAGE:-amc-tracker}:${CUSTOM_TAG:-latest} (first time takes a few minutes)"
	docker compose build
fi

# 3. Stack + site
step "Starting the stack"
docker compose up -d

step "Waiting for the site $SITE_NAME"
for _ in $(seq 1 90); do
	state=$(docker compose ps -a create-site --format '{{.State}} {{.ExitCode}}' 2>/dev/null || true)
	case "$state" in
		"exited 0") break ;;
		exited*) docker compose logs --tail=40 create-site; echo "create-site failed ($state). See docs/TROUBLESHOOTING.md." >&2; exit 1 ;;
	esac
	sleep 10
done
[[ "$state" == "exited 0" ]] || { echo "Timed out waiting for create-site. Check: docker compose logs create-site" >&2; exit 1; }

bench() { docker compose exec -T backend bench --site "$SITE_NAME" "$@"; }
for _ in $(seq 1 30); do bench list-apps >/dev/null 2>&1 && break; sleep 5; done

# 4. Skip the setup wizard (a frappe-only site shows it on first login)
if bench execute frappe.is_setup_complete 2>/dev/null | tail -n 1 | grep -qi true; then
	echo "    setup wizard already completed"
else
	step "Completing the setup wizard (Qatar, Asia/Qatar, QAR)"
	bench execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
		--kwargs '{"args": {"language": "English", "country": "Qatar", "timezone": "Asia/Qatar", "currency": "QAR"}}' >/dev/null
	bench execute amc_tracker.setup.install.set_system_time_zone --kwargs '{"time_zone": "Asia/Qatar"}' >/dev/null
fi

# 5. Optional demo data
demo_password=""
if (( demo )); then
	step "Creating demo users, clients and AMCs"
	demo_password=$(random_password)
	bench execute amc_tracker.setup.demo.create_test_users --kwargs "{\"password\": \"$demo_password\"}" >/dev/null
	bench execute amc_tracker.setup.demo.configure_test_settings >/dev/null
	bench execute amc_tracker.setup.demo.create_test_data >/dev/null
fi

step "Done"
cat <<EOF
    Open:      ${HOST_NAME}   (use this hostname: real-time pop-ups need it)
    Log in:    Administrator / ADMIN_PASSWORD from .env
EOF
if [[ -n "$demo_password" ]]; then
	cat <<EOF
    Demo users (password: $demo_password)
               helpdesk@amc.test, eng1..eng4@amc.test, am@amc.test, tm@amc.test
               Remove them later: docker compose exec backend bench --site $SITE_NAME execute amc_tracker.setup.demo.delete_test_data
EOF
fi
cat <<EOF
    Next:      Office 365 email account (README section 6) and AMC Settings (section 7).
EOF
