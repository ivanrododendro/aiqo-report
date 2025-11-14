/**
 * Global Synthesis component: renders the daily chart, legend, and formats global stats.
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  const GlobalSynthesis = {
    _initialized: false,
    init() {
      if (this._initialized) return;
      this._initialized = true;

      this._renderDailyChart();
      this._attachDailyChartClick();
      this._populateOptimizationLegend();
      this._formatGlobalQueryDurations();
    },

    _renderDailyChart() {
      try {
        if (window.reportChartManager) {
          window.reportChartManager.renderDailyCumulatedTimeChart();
        }
      } catch (e) {
        console.error('Daily chart render failed:', e);
      }
    },

    _attachDailyChartClick() {
      const dailyChartCanvas = document.getElementById('dailyCumulatedTimeChart');
      if (!dailyChartCanvas) return;
      dailyChartCanvas.onclick = (evt) => {
        const chart = window.reportChartManager && window.reportChartManager.charts
          ? window.reportChartManager.charts.dailyCumulatedTime
          : null;
        if (!chart) return;
        const points = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
        if (!points.length) return;
        const idx = points[0].index;
        const day = chart.data.labels[idx];
        if (window.reportNavigator) {
          window.reportNavigator.navigateToDay(day);
        }
      };
    },

    _populateOptimizationLegend() {
      const legendEntries =
        (window.reportData &&
          reportData.optimizations &&
          reportData.optimizations.annotations &&
          reportData.optimizations.annotations.legend_entries &&
          reportData.optimizations.annotations.legend_entries.generic) ||
        [];

      const serverContainer = document.getElementById('genericOptimizationLegendServer');
      const eventsContainer = document.getElementById('genericOptimizationLegendEvents');
      if (!serverContainer || !eventsContainer) return;

      const badge = (date) =>
        date ? `<span class="badge bg-secondary bg-opacity-75 ms-2">${date}</span>` : '';

      const serverEntries = legendEntries
        .filter((entry) => entry.type === 'Serveur')
        .sort((a, b) => a.id.localeCompare(b.id));
      const eventEntries = legendEntries
        .filter((entry) => entry.type === 'Événement')
        .sort((a, b) => a.id.localeCompare(b.id));

      serverContainer.innerHTML = serverEntries
        .map(
          (entry) =>
            `(<strong>${entry.id}</strong>) <code>${entry.text}</code>${badge(entry.date)}`
        )
        .join('<br/>');

      eventsContainer.innerHTML = eventEntries
        .map(
          (entry) =>
            `(<strong>${entry.id}</strong>) ${entry.text}${badge(entry.date)}`
        )
        .join('<br/>');
    },

    _formatGlobalQueryDurations() {
      const stats = (window.reportData && reportData.statistics && reportData.statistics.global_query_stats) || [];
      stats.forEach((stat) => {
        const safeCode = ReportUtils.safeId(stat.code);
        const el = document.getElementById('cumulated-time-' + safeCode);
        if (el) {
          el.innerHTML = Duration.fromMillis(stat.cumulated_time).toFormat("h'h'm'm's's'");
        }
      });
    },
  };

  AIQO.Components.GlobalSynthesis = GlobalSynthesis;
})();
