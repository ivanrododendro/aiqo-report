/**
 * Query Details component: initializes per-query panels (stats, PEV2, per-query charts)
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};
  const queryAccordionState = {
    stats: true,
    ai: false,
    queryopt: false,
    pev2: false,
    chart: false,
  };
  const queryAnnotationToggleState = {
    initialized: false,
    includeQuery: true,
    includeServer: false,
    includeGeneric: false,
  };

  function initializeQueryAnnotationStateFromDom() {
    if (queryAnnotationToggleState.initialized) return;

    const queryToggle = document.querySelector('[data-query-annotation-key="includeQuery"]');
    const serverToggle = document.querySelector('[data-query-annotation-key="includeServer"]');
    const genericToggle = document.querySelector('[data-query-annotation-key="includeGeneric"]');

    if (queryToggle) queryAnnotationToggleState.includeQuery = !!queryToggle.checked;
    if (serverToggle) queryAnnotationToggleState.includeServer = !!serverToggle.checked;
    if (genericToggle) queryAnnotationToggleState.includeGeneric = !!genericToggle.checked;

    queryAnnotationToggleState.initialized = true;
  }

  function syncQueryAnnotationControls(sourceEl) {
    document
      .querySelectorAll('[data-query-annotation-key]')
      .forEach((inputEl) => {
        if (inputEl === sourceEl) return;
        const { queryAnnotationKey } = inputEl.dataset;
        if (!queryAnnotationKey || !(queryAnnotationKey in queryAnnotationToggleState)) return;
        inputEl.checked = !!queryAnnotationToggleState[queryAnnotationKey];
      });
  }

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

  function updateAccordionButtonState(collapseEl, isOpen) {
    if (!collapseEl || !collapseEl.id) return;
    const selector = `[data-bs-target="#${collapseEl.id}"]`;
    const button = document.querySelector(selector);
    if (!button) return;

    button.classList.toggle('collapsed', !isOpen);
    button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }

  function setAccordionDomState(collapseEl, shouldOpen) {
    if (!collapseEl) return;

    collapseEl.classList.add('collapse');
    collapseEl.classList.remove('collapsing');
    collapseEl.classList.toggle('show', shouldOpen);
    collapseEl.style.height = '';
    updateAccordionButtonState(collapseEl, shouldOpen);
  }

  function syncAccordionsByKey(queryAccordionKey, shouldOpen, sourceEl) {
    document
      .querySelectorAll(`.accordion-collapse[data-query-accordion-key="${queryAccordionKey}"]`)
      .forEach((collapseEl) => {
        if (collapseEl === sourceEl) {
          updateAccordionButtonState(collapseEl, shouldOpen);
          return;
        }
        setAccordionDomState(collapseEl, shouldOpen);
      });
  }

  function bindAccordionStateHandlers(appId) {
    const accordionRoot = document.getElementById(`accordion-${appId}`);
    if (!accordionRoot || accordionRoot.dataset.accordionStateBound === 'true') return;

    accordionRoot
      .querySelectorAll('.accordion-collapse[data-query-accordion-key]')
      .forEach((collapseEl) => {
        const { queryAccordionKey } = collapseEl.dataset;
        if (!queryAccordionKey) return;

        collapseEl.addEventListener('shown.bs.collapse', () => {
          queryAccordionState[queryAccordionKey] = true;
          updateAccordionButtonState(collapseEl, true);
          syncAccordionsByKey(queryAccordionKey, true, collapseEl);
        });
        collapseEl.addEventListener('hidden.bs.collapse', () => {
          queryAccordionState[queryAccordionKey] = false;
          updateAccordionButtonState(collapseEl, false);
          syncAccordionsByKey(queryAccordionKey, false, collapseEl);
        });
      });

    accordionRoot.dataset.accordionStateBound = 'true';
  }

  function applyAccordionState(appId) {
    const accordionRoot = document.getElementById(`accordion-${appId}`);
    if (!accordionRoot) return;

    accordionRoot
      .querySelectorAll('.accordion-collapse[data-query-accordion-key]')
      .forEach((collapseEl) => {
        const { queryAccordionKey } = collapseEl.dataset;
        if (!queryAccordionKey || !(queryAccordionKey in queryAccordionState)) return;

        const shouldOpen = !!queryAccordionState[queryAccordionKey];
        setAccordionDomState(collapseEl, shouldOpen);
      });
  }

  function findScrollableParent(el) {
    let current = el ? el.parentElement : null;

    while (current) {
      const style = window.getComputedStyle(current);
      const canScrollY = /(auto|scroll)/.test(style.overflowY);
      if (canScrollY && current.scrollHeight > current.clientHeight) {
        return current;
      }
      current = current.parentElement;
    }

    return null;
  }

  function scrollToFirstOpenAccordion(appId) {
    const accordionRoot = document.getElementById(`accordion-${appId}`);
    if (!accordionRoot) return;

    const firstOpenCollapse = accordionRoot.querySelector('.accordion-collapse.show');
    if (!firstOpenCollapse) return;

    const header = firstOpenCollapse.previousElementSibling;
    const scrollTarget = header || firstOpenCollapse;
    const scrollParent = findScrollableParent(accordionRoot);

    if (scrollParent) {
      const parentRect = scrollParent.getBoundingClientRect();
      const targetRect = scrollTarget.getBoundingClientRect();
      const offsetTop = targetRect.top - parentRect.top + scrollParent.scrollTop - 12;

      scrollParent.scrollTo({
        top: Math.max(offsetTop, 0),
        behavior: 'smooth',
      });
      return;
    }

    scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        <div class="col-auto"><strong>Start:</strong> ${validStart}</div>
        <div class="col-auto"><strong>End:</strong> ${validEnd}</div>
        <div class="col-auto"><strong>Duration:</strong> ${durationFmt}</div>
        <div class="col-auto"><strong>Cost:</strong> ${costFormatted}</div>
        <div class="col-auto"><strong>Rows:</strong> ${rowsFormatted}</div>
      </div>`;
  }

  function isPev2ReadyToMount(appId) {
    const container = document.getElementById(appId);
    if (!container) return false;

    const pev2Collapse = container.closest('.accordion-collapse[data-query-accordion-key="pev2"]');
    if (pev2Collapse && !pev2Collapse.classList.contains('show')) return false;

    return isElementVisible(container);
  }

  function createPev2Markup() {
    return '<pev2 :plan-source="plan" :plan-query="query" style="display: block; aspect-ratio: 16 / 9; width: 100%;"></pev2>';
  }

  function teardownPev2(container) {
    if (!container) return;

    if (container._aiqoPev2App && typeof container._aiqoPev2App.unmount === 'function') {
      try {
        container._aiqoPev2App.unmount();
      } catch (error) {
        console.error('Error unmounting pev2:', error);
      }
    }

    container._aiqoPev2App = null;
    container.innerHTML = createPev2Markup();
  }

  function schedulePev2Mount(appId, report, options = {}) {
    const container = document.getElementById(appId);
    if (!container) return;

    const mountTicket = (container._aiqoPev2MountTicket || 0) + 1;
    container._aiqoPev2MountTicket = mountTicket;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const targetContainer = document.getElementById(appId);
        if (!targetContainer || targetContainer._aiqoPev2MountTicket !== mountTicket) return;
        mountPev2(appId, report, options);
      });
    });
  }

  function mountPev2(appId, report, options = {}) {
    const { forceRemount = false } = options;
    const container = document.getElementById(appId);
    if (!container) return;

    const alreadyMounted = container.hasAttribute('data-v-app') || !!container._aiqoPev2App;
    if (alreadyMounted && !forceRemount) return;
    if (alreadyMounted) {
      teardownPev2(container);
    }

    if (!isPev2ReadyToMount(appId)) return;

    try {
      const planData = report.plan;
      const queryData = report.query_text;

      if (!planData) {
        container.innerHTML = '<div class="alert alert-warning">Execution plan unavailable</div>';
        return;
      }
      if (typeof planData === 'string' && planData.trim().length === 0) {
        container.innerHTML = '<div class="alert alert-warning">Execution plan is empty</div>';
        return;
      }
      if (typeof planData === 'object' && Object.keys(planData).length === 0) {
        container.innerHTML = '<div class="alert alert-warning">Execution plan is empty</div>';
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
          container.innerHTML = '<div class="alert alert-danger">Error converting execution plan</div>';
          return;
        }
      } else {
        container.innerHTML = '<div class="alert alert-danger">Invalid execution plan format</div>';
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
      container._aiqoPev2App = app;
    } catch (error) {
      console.error(`Error mounting pev2 for ${appId}:`, error);
      container.innerHTML = `<div class="alert alert-danger">Error loading execution plan: ${error.message}</div>`;
    }
  }

  function buildAllExecutionsForCode(currentReport, currentDay) {
    const allDays = (window.reportData && reportData.charts && reportData.charts.all_dates) || [];
    const byDay = (window.reportData && reportData.reports && reportData.reports.by_day) || {};
    const currentDayReports = Array.isArray(byDay[currentDay]) ? byDay[currentDay] : [];
    const currentDayMatches = currentDayReports
      .map((report, index) => ({ report, index }))
      .filter(({ report }) => report && report.code === currentReport.code);
    const currentOccurrenceIndex = Math.max(
      currentDayMatches.findIndex(({ report }) => report === currentReport),
      0
    );
    const list = [];

    allDays.forEach((d) => {
      const reps = Array.isArray(byDay[d]) ? byDay[d] : [];
      const matches = reps
        .map((report, index) => ({ report, index }))
        .filter(({ report }) => report && report.code === currentReport.code);
      const matchedExecution = matches[currentOccurrenceIndex] || matches[0] || null;

      if (matchedExecution) {
        const { report, index } = matchedExecution;
        list.push({
          day: d,
          targetIndex: index,
          timestamp: report.query_timestamp,
          duration: report.duration,
          cost: report.cost ?? null,
          rows: report.rows ?? null,
          buffers: report.buffers ?? null,
          buffers_bytes: report.buffers_bytes ?? null,
          total_io_bytes: report.total_io_bytes ?? null,
          wal: report.wal ?? null,
        });
      } else {
        list.push({
          day: d,
          targetIndex: null,
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
    const allExecutions = buildAllExecutionsForCode(report, day);
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
        const clickedExecution = allExecutions[idx] || null;
        const clickedDay = (clickedExecution && clickedExecution.day) || chart.data.labels[idx];
        const targetIndex = clickedExecution && Number.isInteger(clickedExecution.targetIndex)
          ? clickedExecution.targetIndex
          : null;

        if (window.reportNavigator && targetIndex !== null) {
          window.reportNavigator.navigateToQueryInstance(clickedDay, targetIndex);
          return;
        }

        if (window.reportNavigator) {
          window.reportNavigator.navigateToQuery(report.code, clickedDay);
        }
      };

      // Wire annotation toggles for this chart instance
      initializeQueryAnnotationStateFromDom();
      const elQuery = document.getElementById(`toggle-ann-query-${appId}`);
      const elServer = document.getElementById(`toggle-ann-server-${appId}`);
      const elGeneric = document.getElementById(`toggle-ann-generic-${appId}`);

      const toggleSection = (el, show) => {
        if (!el) return;
        el.classList.add('fade-toggle');
        if (show) {
          el.classList.remove('is-hidden');
          el.classList.add('is-shown');
        } else {
          el.classList.remove('is-shown');
          el.classList.add('is-hidden');
        }
      };

      const applyToggles = () => {
        if (elQuery) elQuery.checked = !!queryAnnotationToggleState.includeQuery;
        if (elServer) elServer.checked = !!queryAnnotationToggleState.includeServer;
        if (elGeneric) elGeneric.checked = !!queryAnnotationToggleState.includeGeneric;
        syncQueryAnnotationControls();

        if (window.reportChartManager) {
          window.reportChartManager.updateQueryAnnotations(chartId, report.code, day, queryAnnotationToggleState);
        }

        // Also toggle the under-chart lists with a quick animation
        const serverList = document.getElementById(`under-chart-server-list-${appId}`);
        const eventList = document.getElementById(`under-chart-event-list-${appId}`);
        toggleSection(serverList, !!queryAnnotationToggleState.includeServer);
        toggleSection(eventList, !!queryAnnotationToggleState.includeGeneric);
      };

      if (elQuery) {
        elQuery.onchange = () => {
          queryAnnotationToggleState.includeQuery = !!elQuery.checked;
          syncQueryAnnotationControls(elQuery);
          applyToggles();
        };
      }
      if (elServer) {
        elServer.onchange = () => {
          queryAnnotationToggleState.includeServer = !!elServer.checked;
          syncQueryAnnotationControls(elServer);
          applyToggles();
        };
      }
      if (elGeneric) {
        elGeneric.onchange = () => {
          queryAnnotationToggleState.includeGeneric = !!elGeneric.checked;
          syncQueryAnnotationControls(elGeneric);
          applyToggles();
        };
      }

      // Initial application to ensure defaults are reflected
      applyToggles();
    }
  }

  function refreshQueryChart(appId) {
    if (!window.reportChartManager || !window.reportChartManager.charts) return;
    const chartId = `execTimeChart-${appId}`;
    const chart = window.reportChartManager.charts[chartId];
    if (!chart) return;

    chart.resize();
    chart.update('none');
  }

  function bindDetailSectionHandlers(appId, day, report) {
    const accordionRoot = document.getElementById(`accordion-${appId}`);
    if (!accordionRoot || accordionRoot.dataset.detailSectionHandlersBound === 'true') return;

    const chartCollapse = accordionRoot.querySelector(
      '.accordion-collapse[data-query-accordion-key="chart"]'
    );
    if (chartCollapse) {
      chartCollapse.addEventListener('shown.bs.collapse', () => {
        renderQueryChart(appId, day, report);
        setTimeout(() => refreshQueryChart(appId), 0);
      });
    }

    const pev2Collapse = accordionRoot.querySelector(
      '.accordion-collapse[data-query-accordion-key="pev2"]'
    );
    if (pev2Collapse) {
      pev2Collapse.addEventListener('shown.bs.collapse', () => {
        schedulePev2Mount(appId, report, { forceRemount: true });
        setTimeout(() => refreshQueryChart(appId), 0);
      });
    }

    accordionRoot.dataset.detailSectionHandlersBound = 'true';
  }

  function safeInitForTab(tabEl) {
    const ids = deriveIdsFromQueryTabId(tabEl.id);
    if (!ids) return;
    const { safeDay, index, appId } = ids;
    const day = safeDay; // days are safe-id equals YYYY-MM-DD
    const generalStatsId = `query-details-general-${appId}`;
    const queryPaneId = `query-content-${safeDay}-${index}`;

    // Wait for the active query pane to be visible before initializing its content.
    const fn = function () {
      const queryPane = document.getElementById(queryPaneId);
      if (!isElementVisible(queryPane)) {
        setTimeout(fn, 150);
        return;
      }
      const report = getReportFor(day, index);
      if (!report) return;
      bindAccordionStateHandlers(appId);
      bindDetailSectionHandlers(appId, day, report);
      applyAccordionState(appId);
      formatGeneralStats(generalStatsId, report);
      requestAnimationFrame(() => scrollToFirstOpenAccordion(appId));
      if (queryAccordionState.pev2) {
        schedulePev2Mount(appId, report, { forceRemount: true });
      }
      renderQueryChart(appId, day, report);
    };
    fn();
  }

  function getVisibleDaySafeId() {
    const visibleDayContent = document.querySelector('.day-tab-content:not(.d-none)');
    if (visibleDayContent) {
      const activePane = visibleDayContent.querySelector('.tab-pane.show.active');
      if (activePane && activePane.id && activePane.id.indexOf('tab-day-') === 0) {
        return activePane.id.replace('tab-day-', '');
      }
    }

    const activeDayInVisibleContainer = document.querySelector(
      '.day-tabs-container:not(.d-none) .day-tabs .nav-link.active'
    );
    if (activeDayInVisibleContainer) {
      return activeDayInVisibleContainer.id.replace('tab-day-', '').replace(/-tab$/, '');
    }

    const fallbackActive = document.querySelector('.day-tabs .nav-link.active');
    if (fallbackActive) {
      return fallbackActive.id.replace('tab-day-', '').replace(/-tab$/, '');
    }
    return null;
  }

  function findQueryTabForDay(safeDay) {
    if (!safeDay) return null;
    const dayPane = document.getElementById(`tab-day-${safeDay}`);
    if (dayPane) {
      const activeQuery = dayPane.querySelector('.query-gantt-row.active');
      if (activeQuery) return activeQuery;
      const fallbackQuery = dayPane.querySelector('.query-gantt-row');
      if (fallbackQuery) return fallbackQuery;
    }
    return document.querySelector(`[id^="query-tab-${safeDay}-"]`);
  }

  function initListeners() {
    // Initialize on query tab shown
    document.querySelectorAll('[id^="query-tab-"]').forEach((tabEl) => {
      tabEl.addEventListener('shown.bs.tab', function () {
        safeInitForTab(tabEl);
      });
    });

    // Initialize the first query for the currently active day (if any)
    const safeDay = getVisibleDaySafeId();
    if (safeDay) {
      const initialQueryTab = findQueryTabForDay(safeDay);
      if (initialQueryTab) {
        setTimeout(() => safeInitForTab(initialQueryTab), 100);
      }
    }

    // When a day tab is shown, initialize the first query tab for that day
    document.querySelectorAll('[id^="tab-day-"]').forEach((dayTabBtn) => {
      if (!/-tab$/.test(dayTabBtn.id)) return;
      dayTabBtn.addEventListener('shown.bs.tab', function () {
        const safeDay = dayTabBtn.id.replace('tab-day-', '').replace(/-tab$/, '');
        const targetQueryTab = findQueryTabForDay(safeDay);
        if (targetQueryTab) {
          setTimeout(() => safeInitForTab(targetQueryTab), 100);
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
