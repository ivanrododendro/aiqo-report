/**
 * Global Synthesis component: renders the daily chart, legend, and formats global stats.
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  const normalizeType = (value) => {
    if (!value && value !== 0) return null;
    const normalized = String(value).trim().toLowerCase();
    if (['server', 'serveur'].includes(normalized)) return 'Server';
    if (['query', 'requete', 'requête'].includes(normalized)) return 'Query';
    if (['event', 'événement', 'evenement', 'evento'].includes(normalized)) return 'Event';
    return value;
  };

  const GlobalSynthesis = {
    _initialized: false,
    init() {
      if (this._initialized) return;
      this._initialized = true;

      this._renderDailyChart();
      this._attachDailyChartClick();
      this._populateOptimizationLegend();
      this._formatGlobalQueryDurations();
      this._setupAnnotationToggles();
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

      const badge = (date, type) => {
        if (!date) return '';
        const normalizedType = normalizeType(type);
        let cls = 'badge-annotation-event';
        if (normalizedType === 'Server') cls = 'badge-annotation-server';
        else if (normalizedType === 'Query') cls = 'badge-annotation-query';
        return `<span class="badge ${cls} ms-2">${date}</span>`;
      };

      const normalizedEntries = legendEntries.map((entry) => {
        if (!entry || typeof entry !== 'object') return entry;
        if (!('type' in entry)) return entry;
        return Object.assign({}, entry, { type: normalizeType(entry.type) });
      });

      const serverEntries = normalizedEntries
        .filter((entry) => entry && entry.type === 'Server')
        .sort((a, b) => a.id.localeCompare(b.id));
      const eventEntries = normalizedEntries
        .filter((entry) => entry && entry.type === 'Event')
        .sort((a, b) => a.id.localeCompare(b.id));

      serverContainer.innerHTML = serverEntries
        .map(
          (entry) =>
            `(<strong>${entry.id}</strong>) <code>${entry.text}</code>${badge(entry.date, entry.type)}`
        )
        .join('<br/>');

      eventsContainer.innerHTML = eventEntries
        .map(
          (entry) =>
            `(<strong>${entry.id}</strong>) ${entry.text}${badge(entry.date, entry.type)}`
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

    _setupAnnotationToggles() {
      const serverToggle = document.getElementById('toggle-global-server');
      const eventsToggle = document.getElementById('toggle-global-events');
      const serverCard = document.getElementById('legend-server-card');
      const eventsCard = document.getElementById('legend-events-card');

      const apply = () => {
        const includeServer = !serverToggle || !!serverToggle.checked;
        const includeEvents = !eventsToggle || !!eventsToggle.checked;

        if (window.reportChartManager && typeof window.reportChartManager.updateDailyAnnotations === 'function') {
          window.reportChartManager.updateDailyAnnotations({
            includeServer,
            includeEvents,
          });
        }

        if (serverCard) {
          serverCard.classList.toggle('d-none', !includeServer);
        }
        if (eventsCard) {
          eventsCard.classList.toggle('d-none', !includeEvents);
        }
      };

      if (serverToggle) serverToggle.addEventListener('change', apply);
      if (eventsToggle) eventsToggle.addEventListener('change', apply);
      apply();
    },
  };

  AIQO.Components.GlobalSynthesis = GlobalSynthesis;
})();
