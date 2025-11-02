/**
 * Query Details component: initializes per-query panels (stats, PEV2, per-query charts)
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  function isElementVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.display !== 'none' &&
      style.visibility !== 'hidden'
    );
  }

  function deriveIdsFromQueryTabId(tabId) {
    // tabId format: query-tab-<YYYY-MM-DD>-<index>
    const m = tabId && tabId.match(/^query-tab-(.+)-(\d+)$/);
    if (!m) return null;
    const safeDay = m[1];
    const index = parseInt(m[2], 10);
    const appId = `app-${safeDay}-${index}`;
    return { safeDay, index, appId };
  }

  function getReportFor(day, index) {
    const byDay = (window.reportData && reportData.reports && reportData.reports.by_day) || {};
    const list = byDay[day];
    if (!Array.isArray(list)) return null;
    return list[index] || null;
  }

  function formatGeneralStats(containerId, report) {
    const container = document.getElementById(containerId);
    if (!container || !report) return;

    const durationMillis = Number.isFinite(report.duration) ? report.duration : null;
    const timestampUtc = report.query_timestamp_utc || null;
    let endTime = null;
    if (timestampUtc && Number.isFinite(timestampUtc)) {
      endTime = luxon.DateTime.fromMillis(timestampUtc, { zone: 'utc' });
    }

    let validStart = 'N/A';
    if (endTime && endTime.isValid && Number.isFinite(durationMillis) && durationMillis > 0) {
      const startMillis = endTime.toMillis() - durationMillis;
      if (startMillis > 0) {
        const startTime = luxon.DateTime.fromMillis(startMillis, { zone: 'utc' });
        if (startTime.isValid) {
          validStart = startTime.toFormat('yyyy-MM-dd HH:mm:ss');
        }
      }
    }

    const validEnd = endTime && endTime.isValid
      ? endTime.toFormat('yyyy-MM-dd HH:mm:ss')
      : (timestampUtc ? new Date(timestampUtc).toISOString() : 'N/A');
    const durationFmt = (Number.isFinite(durationMillis) && durationMillis > 0)
      ? luxon.Duration.fromMillis(durationMillis).toFormat("h'h'm'm's's'")
      : 'N/A';

    const cost = report.cost;
    const rows = report.rows;
    const costFormatted = (cost !== null && !isNaN(cost))
      ? Number(cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : 'N/A';
    const rowsFormatted = (rows !== null && !isNaN(rows))
      ? Number(rows).toLocaleString()
      : 'N/A';

    container.innerHTML = `
      <div class="row gy-2 gx-3 text-nowrap">
        <div class="col-auto"><strong>Début :</strong> ${validStart}</div>
        <div class="col-auto"><strong>Fin :</strong> ${validEnd}</div>
        <div class="col-auto"><strong>Durée :</strong> ${durationFmt}</div>
        <div class="col-auto"><strong>Coût :</strong> ${costFormatted}</div>
        <div class="col-auto"><strong>Lignes :</strong> ${rowsFormatted}</div>
      </div>`;
  }

  function mountPev2(appId, report) {
    const container = document.getElementById(appId);
    if (!container) return;
    if (container.hasAttribute('data-v-app')) return; // already mounted

    try {
      const planData = report.plan;
      const queryData = report.query_text;

      if (!planData) {
        container.innerHTML = '<div class="alert alert-warning">Piano di esecuzione non disponibile</div>';
        return;
      }
      if (typeof planData === 'string' && planData.trim().length === 0) {
        container.innerHTML = '<div class="alert alert-warning">Piano di esecuzione vuoto</div>';
        return;
      }
      if (typeof planData === 'object' && Object.keys(planData).length === 0) {
        container.innerHTML = '<div class="alert alert-warning">Piano di esecuzione vuoto</div>';
        return;
      }

      let planString;
      if (typeof planData === 'string') {
        planString = planData;
      } else if (typeof planData === 'object') {
        try {
          planString = JSON.stringify(planData, null, 2);
        } catch (e) {
          console.error('Error stringifying plan data:', e);
          container.innerHTML = '<div class="alert alert-danger">Errore nella conversione del piano di esecuzione</div>';
          return;
        }
      } else {
        container.innerHTML = '<div class="alert alert-danger">Formato del piano di esecuzione non valido</div>';
        return;
      }

      const app = createApp({
        data() {
          return { plan: planString, query: queryData || '' };
        },
        errorCaptured(err, instance, info) {
          console.error('Vue error in pev2:', err, info);
          return false;
        }
      });
      app.component('pev2', pev2.Plan);
      app.mount(`#${appId}`);
    } catch (error) {
      console.error(`Error mounting pev2 for ${appId}:`, error);
      container.innerHTML = `<div class="alert alert-danger">Errore nel caricamento del piano di esecuzione: ${error.message}</div>`;
    }
  }

  function buildAllExecutionsForCode(queryCode) {
    const allDays = (window.reportData && reportData.charts && reportData.charts.all_dates) || [];
    const byDay = (window.reportData && reportData.reports && reportData.reports.by_day) || {};
    const list = [];
    allDays.forEach((d) => {
      const reps = Array.isArray(byDay[d]) ? byDay[d] : [];
      let found = null;
      for (let i = 0; i < reps.length; i++) {
        if (reps[i] && reps[i].code === queryCode) {
          found = reps[i];
          break;
        }
      }
      if (found) {
        list.push({
          timestamp: found.query_timestamp,
          duration: found.duration,
          cost: found.cost ?? null,
          rows: found.rows ?? null,
          buffers: found.buffers ?? null,
          buffers_bytes: found.buffers_bytes ?? null,
          total_io_bytes: found.total_io_bytes ?? null,
          wal: found.wal ?? null,
        });
      } else {
        list.push({
          timestamp: d,
          duration: null,
          cost: null,
          rows: null,
          buffers: null,
          buffers_bytes: null,
          total_io_bytes: null,
          wal: null,
        });
      }
    });
    return list;
  }

  function renderQueryChart(appId, day, report) {
    const chartId = `execTimeChart-${appId}`;
    if (window.reportChartManager) {
      window.reportChartManager.destroyChart(chartId);
    }
    const allExecutions = buildAllExecutionsForCode(report.code);
    const chart = window.reportChartManager
      ? window.reportChartManager.renderQueryExecutionChart(
          chartId,
          report.code,
          allExecutions,
          day
        )
      : null;
    const canvas = document.getElementById(chartId);
    if (canvas && chart) {
      canvas.onclick = function (evt) {
        const points = chart.getElementsAtEventForMode(
          evt,
          'nearest',
          { intersect: true },
          false
        );
        if (!points.length) return;
        const idx = points[0].index;
        const clickedDay = chart.data.labels[idx];
        if (window.reportNavigator) {
          window.reportNavigator.navigateToQuery(report.code, clickedDay);
        }
      };
    }
  }

  function safeInitForTab(tabEl) {
    const ids = deriveIdsFromQueryTabId(tabEl.id);
    if (!ids) return;
    const { safeDay, index, appId } = ids;
    const day = safeDay; // days are safe-id equals YYYY-MM-DD
    const generalStatsId = `query-details-general-${appId}`;

    // Wait for visibility to ensure correct sizing (PEV2 and charts)
    const fn = function () {
      const container = document.getElementById(appId);
      if (!isElementVisible(container)) {
        setTimeout(fn, 150);
        return;
      }
      const report = getReportFor(day, index);
      if (!report) return;
      formatGeneralStats(generalStatsId, report);
      mountPev2(appId, report);
      renderQueryChart(appId, day, report);
    };
    fn();
  }

  function initListeners() {
    // Initialize on query tab shown
    document.querySelectorAll('[id^="query-tab-"]').forEach((tabEl) => {
      tabEl.addEventListener('shown.bs.tab', function () {
        safeInitForTab(tabEl);
      });
    });

    // Initialize the first query for the currently active day (if any)
    const activeDayTab = document.querySelector('.day-tabs .nav-link.active');
    if (activeDayTab) {
      const targetPaneId = activeDayTab.getAttribute('data-bs-target').substring(1); // tab-day-YYYY-MM-DD
      const safeDay = targetPaneId.replace('tab-day-', '');
      const firstQueryTab = document.querySelector(`[id^="query-tab-${safeDay}-"]`);
      if (firstQueryTab) {
        setTimeout(() => safeInitForTab(firstQueryTab), 100);
      }
    }

    // When a day tab is shown, initialize the first query tab for that day
    document.querySelectorAll('[id^="tab-day-"]').forEach((dayTabBtn) => {
      if (!/-tab$/.test(dayTabBtn.id)) return;
      dayTabBtn.addEventListener('shown.bs.tab', function () {
        const safeDay = dayTabBtn.id.replace('tab-day-', '').replace(/-tab$/, '');
        const firstQueryTab = document.querySelector(
          `[id^="query-tab-${safeDay}-"]`
        );
        if (firstQueryTab) {
          setTimeout(() => safeInitForTab(firstQueryTab), 100);
        }
      });
    });
  }

  AIQO.Components.QueryDetails = {
    init() {
      initListeners();
    },
  };
})();
