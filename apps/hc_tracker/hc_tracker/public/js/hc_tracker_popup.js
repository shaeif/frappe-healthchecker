// HC Tracker: on-screen pop-up for notification steps.
// Loaded on every desk page via hooks.app_include_js (plain file, no bundling needed).
// The server publishes the real-time event "hc_tracker_popup" to the recipient user; the same
// notification is also stored in the bell (Notification Log), so nothing is lost when offline.

(function () {
	if (window.hc_tracker_popup_loaded) return;
	window.hc_tracker_popup_loaded = true;

	const queue = [];
	let dialog_open = false;

	function strip(html) {
		const div = document.createElement("div");
		div.innerHTML = html || "";
		return (div.textContent || "").replace(/\s+/g, " ").trim();
	}

	function desktop_notification(data) {
		if (!("Notification" in window) || Notification.permission !== "granted") return;
		try {
			const n = new Notification(data.title || __("HC Tracker"), {
				body: strip(data.message).slice(0, 240),
				icon: "/assets/hc_tracker/images/hc_tracker_logo.svg",
				tag: `hc-${data.contract || "general"}-${data.title}`,
			});
			n.onclick = () => {
				window.focus();
				if (data.route) frappe.set_route(data.route);
				n.close();
			};
		} catch (e) {
			// Some browsers only allow notifications from a service worker; ignore.
		}
	}

	function show_next() {
		if (dialog_open || !queue.length) return;
		const data = queue.shift();
		dialog_open = true;

		const d = new frappe.ui.Dialog({
			title: data.title || __("HC Tracker"),
			indicator: data.indicator || "blue",
			fields: [{ fieldname: "body", fieldtype: "HTML" }],
			primary_action_label: data.route ? __("Open Contract") : __("OK"),
			primary_action() {
				d.hide();
				if (data.route) frappe.set_route(data.route);
			},
			secondary_action_label: __("Dismiss"),
			secondary_action() {
				d.hide();
			},
		});

		let extra = "";
		if ("Notification" in window && Notification.permission === "default") {
			extra = `<p class="small text-muted" style="margin-top:8px">
				<a href="#" class="hc-enable-desktop">${__("Enable desktop pop-ups for HC Tracker")}</a></p>`;
		}
		d.fields_dict.body.$wrapper.html(
			`<div class="hc-popup-body" style="max-height:60vh;overflow:auto">${data.message || ""}</div>${extra}`
		);
		d.fields_dict.body.$wrapper.find(".hc-enable-desktop").on("click", (e) => {
			e.preventDefault();
			Notification.requestPermission().then(() => $(e.target).closest("p").remove());
		});

		d.onhide = () => {
			dialog_open = false;
			setTimeout(show_next, 300);
		};
		d.show();
		if (frappe.utils.play_sound) frappe.utils.play_sound("alert");
	}

	function on_popup(data) {
		if (!data) return;
		frappe.show_alert({ message: data.title, indicator: data.indicator || "blue" }, 10);
		desktop_notification(data);
		queue.push(data);
		show_next();
	}

	function bind() {
		if (!frappe.realtime || !frappe.realtime.on) return false;
		frappe.realtime.on("hc_tracker_popup", on_popup);
		return true;
	}

	$(document).on("app_ready", () => {
		if (!window.hc_tracker_popup_bound) window.hc_tracker_popup_bound = bind();
	});
	// In case app_ready already fired before this file was evaluated
	$(() => {
		if (!window.hc_tracker_popup_bound && frappe.boot && frappe.boot.user) {
			window.hc_tracker_popup_bound = bind();
		}
	});
})();
