/**
 * Chart management for the report (creates/destroys charts)
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.ReportChartManager = class ReportChartManager {
  constructor(reportData) {
    this.reportData = reportData;
    this.chartFactory = new AIQO.Core.ChartFactory(reportData);
    this.charts = {};
  }

  renderDailyCumulatedTimeChart() {
    const ctx = document.getElementById('dailyCumulatedTimeChart');
    if (!ctx) {
      console.warn('Daily chart canvas not found');
      return null;
    }
    this.charts.dailyCumulatedTime = this.chartFactory.createDailyCumulatedTimeChart(ctx.getContext('2d'));
    return this.charts.dailyCumulatedTime;
  }

  renderQueryExecutionChart(canvasId, queryCode, allExecutions, selectedDay) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
      console.warn(`Query chart canvas not found: ${canvasId}`);
      return null;
    }
    this.charts[canvasId] = this.chartFactory.createQueryExecutionChart(
      ctx.getContext('2d'),
      canvasId,
      queryCode,
      allExecutions,
      selectedDay
    );
    return this.charts[canvasId];
  }

  // Update annotations on an existing query chart based on toggle options
  updateQueryAnnotations(canvasId, queryCode, selectedDay, options) {
    const chart = this.charts[canvasId];
    if (!chart) return;
    const labels = Array.isArray(chart.data && chart.data.labels) ? chart.data.labels : [];
    const annotations = this.chartFactory.annotationService.buildQueryAnnotations(
      queryCode,
      labels,
      selectedDay,
      options || {}
    );
    if (!chart.options.plugins) chart.options.plugins = {};
    if (!chart.options.plugins.annotation) chart.options.plugins.annotation = {};
    chart.options.plugins.annotation.annotations = annotations;
    chart.update('none');
  }

  updateDailyAnnotations(options) {
    const chart = this.charts.dailyCumulatedTime;
    if (!chart) return;
    const annotations = this.chartFactory.annotationService.buildDailyAnnotations(options || {});
    if (!chart.options.plugins) chart.options.plugins = {};
    if (!chart.options.plugins.annotation) chart.options.plugins.annotation = {};
    chart.options.plugins.annotation.annotations = annotations;
    chart.update('none');
  }

  destroyChart(chartId) {
    if (this.charts[chartId]) {
      this.charts[chartId].destroy();
      delete this.charts[chartId];
    }
  }
}
})();
