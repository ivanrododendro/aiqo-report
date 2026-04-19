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
    compare: false,
    chart: false,
  };
  const queryAnnotationToggleState = {
    initialized: false,
    includeQuery: true,
    includeServer: true,
    includeGeneric: true,
  };
  let planCompareModalState = null;
  let chartContextMenuState = null;

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

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getPev2PlanPayload(report) {
    if (!report) return null;

    const parsedReportPlan = parsePlanStructure(report);
    if (parsedReportPlan) {
      return parsedReportPlan;
    }

    return parsePlanStructure(report.plan);
  }

  function renderRawPlanFallback(container, planData) {
    let rawPlanText = 'Execution plan unavailable';

    if (typeof planData === 'string' && planData.trim().length > 0) {
      rawPlanText = planData;
    } else if (planData && typeof planData === 'object') {
      try {
        rawPlanText = JSON.stringify(planData, null, 2);
      } catch (error) {
        rawPlanText = 'Execution plan available but could not be serialized.';
      }
    }

    container.innerHTML = `
      <div class="alert alert-warning mb-3">
        PEV2 could not render this execution plan. Showing the raw plan instead.
      </div>
      <pre class="border rounded bg-light p-3 mb-0 small" style="white-space: pre-wrap; overflow: auto;">${escapeHtml(rawPlanText)}</pre>
    `;
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

      const pev2Payload = getPev2PlanPayload(report);
      if (!pev2Payload) {
        renderRawPlanFallback(container, planData);
        return;
      }

      let planString;
      try {
        planString = JSON.stringify(pev2Payload, null, 2);
      } catch (e) {
        console.error('Error stringifying plan data:', e);
        container.innerHTML = '<div class="alert alert-danger">Error converting execution plan</div>';
        return;
      }

      if (typeof planString !== 'string' || planString.trim().length === 0) {
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

  function renderPlanComparisonTree(appId, report) {
    const container = document.getElementById(`plan-compare-tree-${appId}`);
    if (!container) return;

    container.innerHTML = '';
    const comparison = report && report.plan_comparison;
    const tree = comparison && comparison.tree;
    if (!tree) {
      const emptyState = document.createElement('div');
      emptyState.className = 'text-muted small';
      emptyState.textContent = 'Semantic tree compare unavailable.';
      container.appendChild(emptyState);
      return;
    }

    container.appendChild(createPlanCompareNodeElement(tree));
  }

  function createPlanCompareNodeElement(node) {
    const nodeEl = document.createElement('div');
    nodeEl.className = `plan-compare-node ${node.status || 'unchanged'}`;

    const rowEl = document.createElement('div');
    rowEl.className = 'plan-compare-row';

    const children = Array.isArray(node.children) ? node.children : [];
    const hasChildren = children.length > 0;
    const isExpanded = !!node.is_expanded;

    const toggleEl = document.createElement('button');
    toggleEl.type = 'button';
    toggleEl.className = 'plan-compare-toggle';
    if (!hasChildren) {
      toggleEl.disabled = true;
      toggleEl.classList.add('empty');
      toggleEl.setAttribute('aria-hidden', 'true');
      toggleEl.textContent = '';
    } else {
      toggleEl.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
      toggleEl.textContent = isExpanded ? '−' : '+';
    }
    rowEl.appendChild(toggleEl);

    const contentEl = document.createElement('div');
    contentEl.className = 'plan-compare-content';

    const labelEl = document.createElement('span');
    labelEl.className = 'plan-compare-label';
    labelEl.textContent = node.current_label || node.baseline_label || node.title || 'Unknown node';
    contentEl.appendChild(labelEl);

    if (node.semantic_annotation) {
      const annotationEl = document.createElement('span');
      annotationEl.className = 'plan-compare-annotation';
      if (node.semantic_annotation.indexOf('changed, was ') === 0) {
        annotationEl.classList.add('annotation-changed-was');
      } else if (node.semantic_annotation === 'changed subtree') {
        annotationEl.classList.add('annotation-changed-subtree');
      } else if (node.semantic_annotation === 'same') {
        annotationEl.classList.add('annotation-same');
      }
      annotationEl.textContent = `[${node.semantic_annotation}]`;
      contentEl.appendChild(annotationEl);
    }

    rowEl.appendChild(contentEl);
    nodeEl.appendChild(rowEl);

    if (hasChildren) {
      const childrenEl = document.createElement('div');
      childrenEl.className = 'plan-compare-children';
      if (!isExpanded) {
        childrenEl.classList.add('is-collapsed');
      }

      children.forEach((child) => {
        childrenEl.appendChild(createPlanCompareNodeElement(child));
      });

      toggleEl.addEventListener('click', () => {
        const collapsed = childrenEl.classList.toggle('is-collapsed');
        toggleEl.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        toggleEl.textContent = collapsed ? '+' : '−';
      });

      nodeEl.appendChild(childrenEl);
    }

    return nodeEl;
  }

  function formatNumberValue(value, fractionDigits = 2) {
    if (!Number.isFinite(value)) return 'N/A';
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
  }

  function formatIntegerValue(value) {
    if (!Number.isFinite(value)) return 'N/A';
    return Math.round(value).toLocaleString();
  }

  function asFiniteNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
  }

  function formatBytesValue(value) {
    if (!Number.isFinite(value)) return 'N/A';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let current = value;
    let unitIndex = 0;
    while (current >= 1024 && unitIndex < units.length - 1) {
      current /= 1024;
      unitIndex += 1;
    }
    return `${current.toFixed(2)} ${units[unitIndex]}`;
  }

  function formatDurationValue(value) {
    if (!Number.isFinite(value)) return 'N/A';
    if (value < 1000) return `${Math.round(value)} ms`;
    if (value < 60000) return `${(value / 1000).toFixed(2)} s`;
    if (value < 3600000) return `${(value / 60000).toFixed(2)} min`;
    return `${(value / 3600000).toFixed(2)} h`;
  }

  function formatDeltaPercent(baselineValue, currentValue) {
    if (!Number.isFinite(baselineValue) || !Number.isFinite(currentValue) || baselineValue === 0) return 'N/A';
    const pct = ((currentValue - baselineValue) / baselineValue) * 100;
    if (Math.abs(pct) < 0.05) return '0%';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
  }

  function classifyComparisonStatus(baselineReport, currentReport) {
    const baselineDuration = Number(baselineReport && baselineReport.duration);
    const currentDuration = Number(currentReport && currentReport.duration);
    if (!Number.isFinite(baselineDuration) || !Number.isFinite(currentDuration) || baselineDuration === 0) {
      return 'secondary';
    }
    const pct = (currentDuration - baselineDuration) / baselineDuration;
    if (pct >= 0.15) return 'warning';
    if (pct <= -0.15) return 'success';
    return 'info';
  }

  function extractWalBytes(report) {
    const wal = report && report.wal;
    return wal ? asFiniteNumber(wal.bytes) : null;
  }

  function buildComparisonMetrics(currentReport, baselineReport) {
    const metrics = [
      {
        label: 'Duration',
        baseline: asFiniteNumber(baselineReport && baselineReport.duration),
        current: asFiniteNumber(currentReport && currentReport.duration),
        formatter: formatDurationValue,
      },
      {
        label: 'Cost',
        baseline: asFiniteNumber(baselineReport && baselineReport.cost),
        current: asFiniteNumber(currentReport && currentReport.cost),
        formatter: (value) => formatNumberValue(value, 2),
      },
      {
        label: 'Rows',
        baseline: asFiniteNumber(baselineReport && baselineReport.rows),
        current: asFiniteNumber(currentReport && currentReport.rows),
        formatter: formatIntegerValue,
      },
      {
        label: 'Total I/O',
        baseline: asFiniteNumber(baselineReport && baselineReport.total_io_bytes),
        current: asFiniteNumber(currentReport && currentReport.total_io_bytes),
        formatter: formatBytesValue,
      },
      {
        label: 'WAL',
        baseline: extractWalBytes(baselineReport),
        current: extractWalBytes(currentReport),
        formatter: formatBytesValue,
      },
    ];

    return metrics.map((metric) => ({
      label: metric.label,
      baselineText: metric.formatter(metric.baseline),
      currentText: metric.formatter(metric.current),
      deltaText: formatDeltaPercent(metric.baseline, metric.current),
    }));
  }

  function parsePlanStructure(planValue) {
    if (!planValue) return null;
    if (typeof planValue === 'object' && planValue.plan_structure && isParsedPlanObject(planValue.plan_structure)) {
      return planValue.plan_structure;
    }
    if (isParsedPlanObject(planValue)) {
      return planValue;
    }
    if (typeof planValue !== 'string') return null;

    let parsed = null;
    try {
      parsed = JSON.parse(planValue);
    } catch (error) {
      parsed = null;
    }

    if (isParsedPlanObject(parsed)) {
      return parsed;
    }

    return parseTextPlan(planValue);
  }

  function isParsedPlanObject(value) {
    return !!(value && typeof value === 'object' && value.Plan && typeof value.Plan === 'object');
  }

  function parseTextPlan(planText) {
    if (typeof planText !== 'string') return null;
    const rootNodes = [];
    const stack = [];
    const lines = planText.split('\n');

    lines.forEach((rawLine) => {
      const line = rawLine.replace(/\r$/, '');
      if (!line.trim()) return;
      if (line.trim().indexOf('Settings:') === 0) return;

      const nodeMatch = line.match(
        /^(?<indent>\s*)(?:->\s*)?(?<descriptor>.+?)\s+\(cost=(?<startup>\d+(?:\.\d+)?)\.\.(?<total>\d+(?:\.\d+)?)\s+rows=(?<rows>\d+).*$/
      );
      if (nodeMatch && nodeMatch.groups) {
        const indent = (nodeMatch.groups.indent || '').length;
        const descriptor = (nodeMatch.groups.descriptor || '').trim();
        const node = {
          'Node Type': extractTextNodeType(descriptor),
          Plans: [],
        };

        const relationName = extractTextRelationName(descriptor);
        const indexName = extractTextIndexName(descriptor);
        const joinType = extractTextJoinType(descriptor);
        if (relationName) node['Relation Name'] = relationName;
        if (indexName) node['Index Name'] = indexName;
        if (joinType) node['Join Type'] = joinType;

        const planRowsMatch = line.match(/\brows=(\d+)/);
        const actualRowsMatch = line.match(/\bactual rows=(\d+)/);
        if (planRowsMatch) node['Plan Rows'] = Number(planRowsMatch[1]);
        if (actualRowsMatch) node['Actual Rows'] = Number(actualRowsMatch[1]);

        while (stack.length && stack[stack.length - 1].indent >= indent) {
          stack.pop();
        }
        if (stack.length) {
          stack[stack.length - 1].node.Plans.push(node);
        } else {
          rootNodes.push(node);
        }
        stack.push({ indent, node });
        return;
      }

      const detailMatch = line.match(/^(?<indent>\s*)(?<detail>.+)$/);
      if (!detailMatch || !detailMatch.groups) return;
      const indent = (detailMatch.groups.indent || '').length;
      const detail = (detailMatch.groups.detail || '').trim();

      let targetNode = null;
      for (let i = stack.length - 1; i >= 0; i -= 1) {
        if (stack[i].indent < indent) {
          targetNode = stack[i].node;
          break;
        }
      }
      if (!targetNode && stack.length) {
        targetNode = stack[stack.length - 1].node;
      }
      if (!targetNode) return;

      applyTextPlanDetail(targetNode, detail);
    });

    if (!rootNodes.length) return null;
    return { Plan: rootNodes[0] };
  }

  function applyTextPlanDetail(node, detail) {
    const workersPlannedMatch = detail.match(/Workers Planned:\s*(\d+)/);
    if (workersPlannedMatch) {
      node['Workers Planned'] = Number(workersPlannedMatch[1]);
      return;
    }

    const workersLaunchedMatch = detail.match(/Workers Launched:\s*(\d+)/);
    if (workersLaunchedMatch) {
      node['Workers Launched'] = Number(workersLaunchedMatch[1]);
    }
  }

  function extractTextNodeType(descriptor) {
    return descriptor.replace(/\s+using\s+.+?\s+on\s+.+$/, '').replace(/\s+on\s+.+$/, '').trim();
  }

  function extractTextRelationName(descriptor) {
    const match = descriptor.match(/\bon\s+([^\s(]+)/);
    return match ? match[1] : null;
  }

  function extractTextIndexName(descriptor) {
    const match = descriptor.match(/\busing\s+([^\s(]+)/);
    return match ? match[1] : null;
  }

  function extractTextJoinType(descriptor) {
    if (descriptor.indexOf(' Join') === -1) return null;
    const joinPrefix = descriptor.split(' Join', 1)[0];
    return ['Inner', 'Left', 'Right', 'Full', 'Semi', 'Anti'].includes(joinPrefix) ? joinPrefix : null;
  }

  function summarizePlanSubtree(node, maxDepth = 2) {
    if (!node || typeof node !== 'object') return '';
    const parts = [];
    let currentNode = node;
    let traversedDepth = 0;

    while (currentNode && typeof currentNode === 'object' && traversedDepth < maxDepth) {
      parts.push(currentNode['Node Type'] || 'Unknown');
      const children = Array.isArray(currentNode.Plans)
        ? currentNode.Plans.filter((child) => child && typeof child === 'object')
        : [];
      if (children.length !== 1) break;
      currentNode = children[0];
      traversedDepth += 1;
    }

    let summary = parts.join(' -> ');
    if (Array.isArray(node.Plans) && node.Plans.length) {
      summary += ' subtree';
    }
    return summary;
  }

  function summarizeTreeDiff(tree) {
    const counts = { changed: 0, changedSubtree: 0, added: 0, removed: 0, unchanged: 0 };

    const walk = (node) => {
      if (!node) return;
      const status = node.status || 'unchanged';
      if (status === 'changed') {
        if (node.semantic_annotation && node.semantic_annotation.indexOf('changed, was ') === 0) {
          counts.changed += 1;
        } else if (node.semantic_annotation === 'changed subtree') {
          counts.changedSubtree += 1;
        }
      } else {
        counts[status] = (counts[status] || 0) + 1;
      }
      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(walk);
    };

    walk(tree);
    return {
      total: counts.changed + counts.changedSubtree + counts.added + counts.removed + counts.unchanged,
      changed: counts.changed,
      changedSubtree: counts.changedSubtree,
      added: counts.added,
      removed: counts.removed,
      unchanged: counts.unchanged,
    };
  }

  function diffPlanNodes(baselineNode, currentNode, path = '0', depth = 0) {
    const children = [];
    let status = 'unchanged';
    let selfStatus = 'unchanged';
    let changes = [];

    if (baselineNode && currentNode) {
      const baselineType = baselineNode['Node Type'] || 'Unknown';
      const currentType = currentNode['Node Type'] || 'Unknown';
      const nodeTypeChanged = baselineType !== currentType;
      changes = nodeTypeChanged ? [`Node type changed from ${baselineType} to ${currentType}.`] : [];
      const baselineChildren = Array.isArray(baselineNode.Plans) ? baselineNode.Plans : [];
      const currentChildren = Array.isArray(currentNode.Plans) ? currentNode.Plans : [];
      children.push(...diffPlanChildren(baselineChildren, currentChildren, path, depth + 1));
      selfStatus = nodeTypeChanged ? 'changed' : 'unchanged';
      const hasChildChanges = children.some((child) => child.status !== 'unchanged');
      status = nodeTypeChanged || hasChildChanges ? 'changed' : 'unchanged';
    } else if (baselineNode) {
      status = 'removed';
      selfStatus = 'removed';
      changes = ['Node removed from the current plan.'];
      const baselineChildren = Array.isArray(baselineNode.Plans) ? baselineNode.Plans : [];
      baselineChildren.forEach((child, index) => {
        if (child && typeof child === 'object') {
          children.push(diffPlanNodes(child, null, `${path}.b${index}`, depth + 1));
        }
      });
    } else if (currentNode) {
      status = 'added';
      selfStatus = 'added';
      changes = ['Node added in the current plan.'];
      const currentChildren = Array.isArray(currentNode.Plans) ? currentNode.Plans : [];
      currentChildren.forEach((child, index) => {
        if (child && typeof child === 'object') {
          children.push(diffPlanNodes(null, child, `${path}.c${index}`, depth + 1));
        }
      });
    }

    const currentLabel = currentNode && currentNode['Node Type'] ? currentNode['Node Type'] : null;
    const baselineLabel = baselineNode && baselineNode['Node Type'] ? baselineNode['Node Type'] : null;

    return {
      path,
      depth,
      status,
      self_status: selfStatus,
      current_label: currentLabel,
      baseline_label: baselineLabel,
      current_subtree_label: summarizePlanSubtree(currentNode),
      baseline_subtree_label: summarizePlanSubtree(baselineNode),
      semantic_annotation: buildSemanticAnnotation(status, selfStatus, baselineLabel),
      changes,
      children,
      is_expanded: depth < 1 || status !== 'unchanged',
    };
  }

  function diffPlanChildren(baselineChildren, currentChildren, parentPath, depth) {
    const normalizedBaseline = baselineChildren.filter((child) => child && typeof child === 'object');
    const normalizedCurrent = currentChildren.filter((child) => child && typeof child === 'object');
    const matchedCurrentIndexes = new Set();
    const children = [];

    normalizedBaseline.forEach((baselineChild, baselineIndex) => {
      const matchIndex = findMatchingChild(baselineChild, normalizedCurrent, matchedCurrentIndexes, baselineIndex);
      if (matchIndex === null) {
        children.push(diffPlanNodes(baselineChild, null, `${parentPath}.b${baselineIndex}`, depth));
        return;
      }

      matchedCurrentIndexes.add(matchIndex);
      children.push(diffPlanNodes(baselineChild, normalizedCurrent[matchIndex], `${parentPath}.${baselineIndex}`, depth));
    });

    normalizedCurrent.forEach((currentChild, currentIndex) => {
      if (matchedCurrentIndexes.has(currentIndex)) return;
      children.push(diffPlanNodes(null, currentChild, `${parentPath}.c${currentIndex}`, depth));
    });

    return children;
  }

  function findMatchingChild(baselineChild, currentChildren, matchedCurrentIndexes, baselineIndex) {
    const baselineSignature = planNodeSignature(baselineChild);
    for (let index = 0; index < currentChildren.length; index += 1) {
      if (matchedCurrentIndexes.has(index)) continue;
      if (planNodeSignature(currentChildren[index]) === baselineSignature) return index;
    }

    const baselineFallbackSignature = planNodeSignature(baselineChild, false);
    for (let index = 0; index < currentChildren.length; index += 1) {
      if (matchedCurrentIndexes.has(index)) continue;
      if (planNodeSignature(currentChildren[index], false) === baselineFallbackSignature) return index;
    }

    if (baselineIndex < currentChildren.length && !matchedCurrentIndexes.has(baselineIndex)) {
      return baselineIndex;
    }
    return null;
  }

  function planNodeSignature(node, includeRelation = true) {
    if (!node || typeof node !== 'object') return null;
    const signature = [node['Node Type'] || null];
    if (includeRelation) {
      signature.push(node['Relation Name'] || null);
      signature.push(node['Index Name'] || null);
    }
    return JSON.stringify(signature);
  }

  function buildSemanticAnnotation(status, selfStatus, baselineLabel) {
    if (status === 'added') return 'added';
    if (status === 'removed') return 'removed';
    if (status === 'unchanged') return 'same';
    if (selfStatus === 'changed') return `changed, was ${baselineLabel || 'Unknown'}`;
    return 'changed subtree';
  }

  function buildPlanComparisonData(currentReport, baselineReport) {
    const currentPlan = parsePlanStructure(currentReport) || parsePlanStructure(currentReport && currentReport.plan);
    const baselinePlan = parsePlanStructure(baselineReport) || parsePlanStructure(baselineReport && baselineReport.plan);
    const tree = currentPlan && baselinePlan ? diffPlanNodes(baselinePlan.Plan, currentPlan.Plan, '0', 0) : null;

    return {
      statusClass: classifyComparisonStatus(baselineReport, currentReport),
      metrics: buildComparisonMetrics(currentReport, baselineReport),
      tree,
      treeSummary: tree ? summarizeTreeDiff(tree) : null,
      treeAvailable: !!tree,
    };
  }

  function createComparisonMetricsTable(metrics) {
    const wrapper = document.createElement('div');
    wrapper.className = 'table-responsive mb-4';

    const table = document.createElement('table');
    table.className = 'table table-sm align-middle mb-0 plan-compare-metrics-table';

    table.innerHTML = `
      <thead>
        <tr>
          <th>Metric</th>
          <th class="text-end">Baseline</th>
          <th class="text-end">Current</th>
          <th class="text-end">Delta</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;

    const tbody = table.querySelector('tbody');
    metrics.forEach((metric) => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td><strong>${metric.label}</strong></td>
        <td class="text-end plan-compare-metric-value">${metric.baselineText}</td>
        <td class="text-end plan-compare-metric-value">${metric.currentText}</td>
        <td class="text-end plan-compare-metric-value">${metric.deltaText}</td>
      `;
      tbody.appendChild(row);
    });

    wrapper.appendChild(table);
    return wrapper;
  }

  function createComparisonSummary(currentReport, baselineReport, comparison) {
    const summary = document.createElement('div');
    summary.className = `alert alert-${comparison.statusClass} mb-4`;
    const currentTs = currentReport && currentReport.query_timestamp ? currentReport.query_timestamp : 'N/A';
    const baselineTs = baselineReport && baselineReport.query_timestamp ? baselineReport.query_timestamp : 'N/A';
    summary.innerHTML = `
      <div class="fw-semibold mb-1">Current execution compared with selected datapoint baseline.</div>
      <div class="small mb-0">Baseline: <strong>${baselineTs}</strong> · Current: <strong>${currentTs}</strong></div>
    `;
    return summary;
  }

  function createQueryTitleBlock(currentReport) {
    const card = document.createElement('div');
    card.className = 'card mb-4';

    const header = document.createElement('div');
    header.className = 'card-header';

    const title = document.createElement('h6');
    title.className = 'mb-0 text-truncate';
    title.style.overflow = 'hidden';
    title.style.whiteSpace = 'nowrap';
    title.style.textOverflow = 'ellipsis';
    title.title = currentReport.title || currentReport.query_name || currentReport.code || '';
    title.textContent = currentReport.title || currentReport.query_name || currentReport.code || 'Query';

    header.appendChild(title);
    card.appendChild(header);
    return card;
  }

  function createTreeSummaryBadges(treeSummary) {
    const badges = document.createElement('div');
    badges.className = 'd-flex flex-wrap gap-2 mb-3';
    badges.innerHTML = `
      <span class="badge text-bg-secondary">Total nodes: ${treeSummary.total}</span>
      <span class="badge status-changed">Changed: ${treeSummary.changed}</span>
      <span class="badge status-changed-subtree">Changed subtree: ${treeSummary.changedSubtree}</span>
      <span class="badge status-added">Added: ${treeSummary.added}</span>
      <span class="badge status-removed">Removed: ${treeSummary.removed}</span>
      <span class="badge status-unchanged">Unchanged: ${treeSummary.unchanged}</span>
    `;
    return badges;
  }

  function ensurePlanCompareModalState() {
    if (planCompareModalState) return planCompareModalState;

    const modalEl = document.getElementById('planCompareModal');
    if (!modalEl) return null;

    planCompareModalState = {
      element: modalEl,
      lastTrigger: null,
    };

    modalEl.addEventListener('hide.bs.modal', () => {
      const activeElement = document.activeElement;
      if (activeElement && modalEl.contains(activeElement) && typeof activeElement.blur === 'function') {
        activeElement.blur();
      }
    });

    modalEl.addEventListener('hidden.bs.modal', () => {
      if (
        planCompareModalState.lastTrigger &&
        typeof planCompareModalState.lastTrigger.focus === 'function' &&
        document.contains(planCompareModalState.lastTrigger)
      ) {
        planCompareModalState.lastTrigger.focus({ preventScroll: true });
      }
      planCompareModalState.lastTrigger = null;
    });

    return planCompareModalState;
  }

  function ensureChartContextMenuState() {
    if (chartContextMenuState) return chartContextMenuState;

    const menuEl = document.createElement('div');
    menuEl.className = 'chart-context-menu d-none';
    menuEl.setAttribute('role', 'menu');
    menuEl.innerHTML = `
      <button type="button" class="chart-context-menu-item" data-action="compare">
        Compare with current query
      </button>
    `;
    document.body.appendChild(menuEl);

    chartContextMenuState = {
      element: menuEl,
      payload: null,
    };

    const hideMenu = () => {
      if (!chartContextMenuState) return;
      chartContextMenuState.payload = null;
      chartContextMenuState.element.classList.add('d-none');
    };

    menuEl.addEventListener('click', (event) => {
      const actionEl = event.target.closest('[data-action]');
      if (!actionEl || !chartContextMenuState.payload) return;

      const { action } = actionEl.dataset;
      const payload = chartContextMenuState.payload;
      hideMenu();

      if (action === 'compare') {
        showPlanCompareModal(payload.currentReport, payload.baselineReport, payload.triggerElement);
      }
    });

    document.addEventListener('click', (event) => {
      if (!chartContextMenuState || chartContextMenuState.element.classList.contains('d-none')) return;
      if (chartContextMenuState.element.contains(event.target)) return;
      hideMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        hideMenu();
      }
    });

    window.addEventListener('scroll', hideMenu, true);
    window.addEventListener('resize', hideMenu);

    chartContextMenuState.hide = hideMenu;
    return chartContextMenuState;
  }

  function showChartContextMenu(x, y, payload) {
    const menuState = ensureChartContextMenuState();
    if (!menuState) return;

    menuState.payload = payload;
    const menuEl = menuState.element;
    menuEl.classList.remove('d-none');
    menuEl.style.left = '0px';
    menuEl.style.top = '0px';

    const rect = menuEl.getBoundingClientRect();
    const maxLeft = Math.max(window.innerWidth - rect.width - 12, 12);
    const maxTop = Math.max(window.innerHeight - rect.height - 12, 12);
    const left = Math.min(Math.max(x, 12), maxLeft);
    const top = Math.min(Math.max(y, 12), maxTop);

    menuEl.style.left = `${left}px`;
    menuEl.style.top = `${top}px`;
  }

  function showPlanCompareModal(currentReport, baselineReport, triggerElement) {
    const modalState = ensurePlanCompareModalState();
    const modalEl = modalState && modalState.element;
    const titleEl = document.getElementById('planCompareModalTitle');
    const subtitleEl = document.getElementById('planCompareModalSubtitle');
    const bodyEl = document.getElementById('planCompareModalBody');
    if (!modalEl || !titleEl || !subtitleEl || !bodyEl) return;

    modalState.lastTrigger = triggerElement || document.activeElement || null;

    const comparison = buildPlanComparisonData(currentReport, baselineReport);
    bodyEl.innerHTML = '';

    titleEl.textContent = 'Plan Compare';
    subtitleEl.textContent = '';
    bodyEl.appendChild(createQueryTitleBlock(currentReport));
    bodyEl.appendChild(createComparisonSummary(currentReport, baselineReport, comparison));
    bodyEl.appendChild(createComparisonMetricsTable(comparison.metrics));

    if (comparison.treeAvailable) {
      bodyEl.appendChild(createTreeSummaryBadges(comparison.treeSummary));
      const treeContainer = document.createElement('div');
      treeContainer.className = 'plan-compare-tree';
      treeContainer.appendChild(createPlanCompareNodeElement(comparison.tree));
      bodyEl.appendChild(treeContainer);
    } else {
      const emptyState = document.createElement('div');
      emptyState.className = 'alert alert-secondary mb-0';
      emptyState.textContent = 'Unable to build a semantic diff for these two plans.';
      bodyEl.appendChild(emptyState);
    }

    bootstrap.Modal.getOrCreateInstance(modalEl).show();
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
      const resolveChartTarget = function (evt) {
        const points = chart.getElementsAtEventForMode(
          evt,
          'nearest',
          { intersect: true },
          false
        );
        if (!points.length) return null;
        const idx = points[0].index;
        const clickedExecution = allExecutions[idx] || null;
        const clickedDay = (clickedExecution && clickedExecution.day) || chart.data.labels[idx];
        const targetIndex = clickedExecution && Number.isInteger(clickedExecution.targetIndex)
          ? clickedExecution.targetIndex
          : null;
        return { clickedDay, targetIndex };
      };

      canvas.onclick = function (evt) {
        const target = resolveChartTarget(evt);
        if (!target) return;
        const { clickedDay, targetIndex } = target;

        if (window.reportNavigator && targetIndex !== null) {
          window.reportNavigator.navigateToQueryInstance(clickedDay, targetIndex);
          return;
        }

        if (window.reportNavigator) {
          window.reportNavigator.navigateToQuery(report.code, clickedDay);
        }
      };

      canvas.oncontextmenu = function (evt) {
        evt.preventDefault();
        const target = resolveChartTarget(evt);
        if (!target || target.targetIndex === null) return false;
        const baselineReport = getReportFor(target.clickedDay, target.targetIndex);
        if (!baselineReport) return false;
        showChartContextMenu(evt.clientX, evt.clientY, {
          currentReport: report,
          baselineReport,
          triggerElement: canvas,
        });
        return false;
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

    const compareCollapse = accordionRoot.querySelector(
      '.accordion-collapse[data-query-accordion-key="compare"]'
    );
    if (compareCollapse) {
      compareCollapse.addEventListener('shown.bs.collapse', () => {
        renderPlanComparisonTree(appId, report);
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
      if (queryAccordionState.compare) {
        renderPlanComparisonTree(appId, report);
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
