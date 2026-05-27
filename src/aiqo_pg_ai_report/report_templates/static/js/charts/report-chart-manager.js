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
    this.dailyDatasetVisibilityState = {};
    this.queryDatasetVisibilityState = {};
  }

  _destroyChartInstance(chartId, canvasEl) {
    if (this.charts[chartId]) {
      this.charts[chartId].destroy();
      delete this.charts[chartId];
    }

    if (!canvasEl || typeof Chart === 'undefined' || typeof Chart.getChart !== 'function') return;

    const existingChart = Chart.getChart(canvasEl);
    if (existingChart) {
      existingChart.destroy();
    }
  }

  renderDailyCumulatedTimeChart() {
    const ctx = document.getElementById('dailyCumulatedTimeChart');
    if (!ctx) {
      console.warn('Daily chart canvas not found');
      return null;
    }
    this._destroyChartInstance('dailyCumulatedTime', ctx);
    this.charts.dailyCumulatedTime = this.chartFactory.createDailyCumulatedTimeChart(
      ctx.getContext('2d'),
      this.dailyDatasetVisibilityState,
      (visibilityState) => {
        this.dailyDatasetVisibilityState = Object.assign({}, visibilityState);
      }
    );
    return this.charts.dailyCumulatedTime;
  }

  renderQueryExecutionChart(canvasId, queryCode, allExecutions, selectedDay) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
      console.warn(`Query chart canvas not found: ${canvasId}`);
      return null;
    }
    this._destroyChartInstance(canvasId, ctx);
    this.charts[canvasId] = this.chartFactory.createQueryExecutionChart(
      ctx.getContext('2d'),
      canvasId,
      queryCode,
      allExecutions,
      selectedDay,
      this.queryDatasetVisibilityState,
      (visibilityState) => {
        this.queryDatasetVisibilityState = Object.assign({}, visibilityState);
      }
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
    this._destroyChartInstance(chartId, document.getElementById(chartId));
  }
}
})();
