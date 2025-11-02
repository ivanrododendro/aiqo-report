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

  destroyChart(chartId) {
    if (this.charts[chartId]) {
      this.charts[chartId].destroy();
      delete this.charts[chartId];
    }
  }
}
})();
