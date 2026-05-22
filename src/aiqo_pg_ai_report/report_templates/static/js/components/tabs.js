/**
 * Tabs component — split pane management, query pane activation,
 * duplicate analysis links.  (Bootstrap tab navigation removed; handled by sidebar.js)
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  AIQO.Components.Tabs = {

    // Track which split instances have been initialized (keyed by container id)
    _splitInited: {},

    init() {
      this._bindDuplicateAnalysisLinks();
    },

    // ── Split pane ──────────────────────────────────────────────────────────

    /**
     * Called by sidebar.navigateToDay to lazily init the split pane for a panel.
     */
    _initSplitForPanel(panel) {
      if (!panel) return;
      const containers = panel.querySelectorAll('[id^="split-container-"]');
      containers.forEach((container) => {
        if (this._splitInited[container.id]) return;
        this._splitInited[container.id] = true;

        const leftPane  = container.querySelector('.split:nth-child(1)');
        const rightPane = container.querySelector('.split:nth-child(2)');
        if (!leftPane || !rightPane || typeof Split !== 'function') return;

        try {
          const splitInstance = Split([leftPane, rightPane], {
            sizes:     [18, 82],
            minSize:   [100, 300],
            gutterSize: 6,
            cursor:    'col-resize',
            gutter(index, direction) {
              const gutter = document.createElement('div');
              gutter.className = 'gutter gutter-' + direction;
              gutter.addEventListener('dblclick', () =>
                AIQO.Components.Tabs._toggleLeftSplitPane(container)
              );
              return gutter;
            },
          });
          container._aiqoSplitState = {
            instance:          splitInstance,
            lastExpandedSizes: [35, 65],
            isCollapsed:       false,
          };
        } catch (e) {
          console.warn('Split init failed for', container.id, e);
        }
      });
    },

    _toggleLeftSplitPane(container) {
      const state = container && container._aiqoSplitState;
      if (!state) return;
      if (state.isCollapsed) {
        state.instance.setSizes(state.lastExpandedSizes || [18, 82]);
        state.isCollapsed = false;
        container.classList.remove('split-left-collapsed');
      } else {
        state.lastExpandedSizes = state.instance.getSizes();
        state.instance.setSizes([0, 100]);
        state.isCollapsed = true;
        container.classList.add('split-left-collapsed');
      }
    },

    // ── Query pane activation ───────────────────────────────────────────────

    /**
     * Activate a query detail pane by index within a day panel.
     * Used by DayTimeline click handler and navigateToQueryInstance.
     */
    _activateQueryByIndex(dayPanel, index) {
      if (!dayPanel) return;
      const safeDay = ReportUtils.dateToSafeId(dayPanel.dataset.day || '');

      // Deactivate all panes in this day
      dayPanel.querySelectorAll('.query-tab-content .tab-pane.show.active').forEach((p) => {
        p.classList.remove('show', 'active');
      });

      const target = document.getElementById('query-content-' + safeDay + '-' + index);
      if (target) {
        target.classList.add('show', 'active');
        this._scrollDetailToFirstOpen(target);
        // Init PEV2 and charts for this pane (idempotent via ticket system)
        if (AIQO.Components.QueryDetails) {
          AIQO.Components.QueryDetails.initForQuery(safeDay, index);
        }
        // Sync timeline selection
        if (AIQO.Components.DayTimeline) {
          AIQO.Components.DayTimeline.highlightBar(safeDay, index);
        }
      }
    },

    _scrollDetailToFirstOpen() {
      // No-op: query details now use tabs; scrolling managed per-pane.
    },

    // ── Duplicate analysis links ────────────────────────────────────────────

    _bindDuplicateAnalysisLinks() {
      document.querySelectorAll('[data-role="duplicate-ai-analysis-link"]').forEach((link) => {
        link.addEventListener('click', (event) => {
          event.preventDefault();
          const targetDay   = link.getAttribute('data-target-day');
          const targetIndex = parseInt(link.getAttribute('data-target-index'), 10);
          if (!targetDay || isNaN(targetIndex)) return;
          this._navigateToDuplicate(targetDay, targetIndex);
        });
      });
    },

    _navigateToDuplicate(targetDay, targetIndex) {
      const safeTargetDay = ReportUtils.dateToSafeId(targetDay);

      const activate = () => {
        const panel = document.getElementById('day-panel-' + safeTargetDay);
        if (panel) {
          this._activateQueryByIndex(panel, targetIndex);
          const targetPane = document.getElementById(
            'query-content-' + safeTargetDay + '-' + targetIndex
          );
          if (targetPane) targetPane.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      };

      const currentDay = window.AIQO && AIQO.Sidebar && AIQO.Sidebar._currentDay;
      if (currentDay && ReportUtils.dateToSafeId(currentDay) === safeTargetDay) {
        activate();
      } else if (window.AIQO && AIQO.Sidebar && AIQO.Sidebar.navigateToDay) {
        AIQO.Sidebar.navigateToDay(targetDay);
        setTimeout(activate, 350);
      } else {
        activate();
      }
    },
  };
})();
