# syntax=docker/dockerfile:1
#
# Custom image = official frappe/erpnext v16 image + the hc_tracker app.
# The site only installs frappe + hc_tracker; ERPNext stays in the image but is NOT installed.
#
# Build:   docker compose build        (or: docker build -t hc-tracker:latest .)
# Pin a release for production, e.g. --build-arg BASE_TAG=v16.50.0

ARG BASE_IMAGE=frappe/erpnext
ARG BASE_TAG=v16
FROM ${BASE_IMAGE}:${BASE_TAG}

USER frappe
WORKDIR /home/frappe/frappe-bench

# 1. Copy the app source into the bench
COPY --chown=frappe:0 apps/hc_tracker /home/frappe/frappe-bench/apps/hc_tracker

# 2. Install it into the bench virtualenv (editable, like `bench get-app` does)
# 3. Register it in the image's apps.txt (the configurator also regenerates sites/apps.txt)
# 4. Publish its static files: the official image serves /assets from /home/frappe/frappe-bench/assets
#    (sites/assets is a symlink created by the entrypoint), so link the app's public folder there.
#    hc_tracker ships only plain JS/SVG (no bundles), so no `bench build` is needed.
RUN env/bin/python -m pip install --no-cache-dir -e apps/hc_tracker \
    && (grep -qx hc_tracker sites/apps.txt || printf '\nhc_tracker\n' >> sites/apps.txt) \
    && sed -i '/^$/d' sites/apps.txt \
    && ln -sfn /home/frappe/frappe-bench/apps/hc_tracker/hc_tracker/public /home/frappe/frappe-bench/assets/hc_tracker \
    && env/bin/python -c "import hc_tracker, hc_tracker.hooks; print('hc_tracker', hc_tracker.__version__, 'installed')"
