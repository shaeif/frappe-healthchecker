frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["HC Tracker Metrics"] = {
	method: "hc_tracker.api.metrics.get",
	filters: [],
};
