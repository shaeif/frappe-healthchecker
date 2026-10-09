frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["AMC Tracker Metrics"] = {
	method: "amc_tracker.api.metrics.get",
	filters: [],
};
