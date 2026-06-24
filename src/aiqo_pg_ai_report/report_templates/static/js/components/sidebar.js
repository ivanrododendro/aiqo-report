/**
 * Sidebar component: heatmap, date tree navigation, view switching.
 */
;(function () {
  window.AIQO = window.AIQO || {};

  AIQO.Sidebar = {
    _currentDay: null,
    _currentView: 'summary',

    init() {
      this._buildHeatmap();
      this._bindTreeNavigation();
      this._bindViewToggles();
      this._bindSectionNavItems();
      this._activateInitialDay();
      this._showView('summary');
    },

    // ── Public navigation API ───────────────────────────────────────────────

    navigateToDay(day) {
      if (!day) return;

      // Hide all day panels
      document.querySelectorAll('.aiqo-day-panel').forEach((p) => p.classList.add('d-none'));

      const safeDay = ReportUtils.dateToSafeId(day);
      const panel = document.getElementById('day-panel-' + safeDay);
      if (!panel) return;

      panel.classList.remove('d-none');
      this._currentDay = day;

      // Ensure days view is visible
      this._showView('days');

      // Update sidebar tree active state
      document.querySelectorAll('.aiqo-tree-day-btn').forEach((b) => {
        b.classList.toggle('active', b.dataset.day === day);
        b.setAttribute('aria-current', b.dataset.day === day ? 'page' : 'false');
      });

      this._openOnlyDayBranch(day);

      // Update heatmap selection
      document.querySelectorAll('.aiqo-heatmap-cell.selected').forEach((c) => c.classList.remove('selected'));
      const hCell = document.querySelector('.aiqo-heatmap-cell[data-day="' + day + '"]');
      if (hCell) hCell.classList.add('selected');

      // Init split panes for this panel (idempotent)
      AIQO.Components.Tabs._initSplitForPanel(panel);

      // Render timeline for this day (lazy, idempotent)
      if (AIQO.Components.DayTimeline) {
        AIQO.Components.DayTimeline.initForDay(day);
      }

      // Init query details (PEV2, charts) for the first visible query pane
      if (AIQO.Components.QueryDetails) {
        AIQO.Components.QueryDetails.initForQuery(safeDay, 0);
      }

      // Update day statistics chips
      if (window.reportNavigator && window.reportNavigator.tabUpdater) {
        window.reportNavigator.tabUpdater.updateTabContent(day);
      }

      window.scrollTo({ top: 0, behavior: 'instant' });
    },

    // ── Heatmap ─────────────────────────────────────────────────────────────

    _buildHeatmap() {
      const container       = document.getElementById('aiqo-heatmap');
      const legendContainer = document.getElementById('aiqo-heatmap-legend-cells');
      if (!container) return;

      const allDays   = (reportData.date_hierarchy || {}).all_days || [];
      const dailyStat = (reportData.statistics || {}).daily_stats  || {};
      if (!allDays.length) return;

      // Max cumulated_time for colour scaling
      let maxTime = 1;
      allDays.forEach((d) => {
        const t = (dailyStat[d] || {}).cumulated_time || 0;
        if (t > maxTime) maxTime = t;
      });

      // Set of days that have reports
      const daysSet = new Set(allDays.filter((d) => dailyStat[d]));

      // Group data days by "YYYY-MM", preserving chronological order
      const monthMap = new Map(); // "YYYY-MM" → Set<"YYYY-MM-DD">
      allDays.forEach((d) => {
        const ym = d.substring(0, 7);
        if (!monthMap.has(ym)) monthMap.set(ym, new Set());
        if (daysSet.has(d)) monthMap.get(ym).add(d);
      });

      // One row per month
      for (const [ym, dataDays] of monthMap) {
        const row = document.createElement('div');
        row.className = 'aiqo-heatmap-month-row';

        const label = document.createElement('span');
        label.className = 'aiqo-heatmap-month-label';
        label.textContent = luxon.DateTime.fromISO(ym + '-01', { zone: 'utc' }).toFormat('MMM yy');
        row.appendChild(label);

        const cellsWrap = document.createElement('div');
        cellsWrap.className = 'aiqo-heatmap-days-row';

        const daysInMonth = luxon.DateTime.fromISO(ym + '-01', { zone: 'utc' }).daysInMonth;
        for (let d = 1; d <= daysInMonth; d++) {
          const dayStr = ym + '-' + String(d).padStart(2, '0');
          const cell   = document.createElement('div');
          cell.className = 'aiqo-heatmap-cell';

          if (dataDays.has(dayStr)) {
            const intensity = (dailyStat[dayStr].cumulated_time || 0) / maxTime;
            const alpha     = Math.round((0.2 + intensity * 0.8) * 255).toString(16).padStart(2, '0');
            cell.style.backgroundColor = '#3b82f6' + alpha;
            cell.classList.add('has-data');
            cell.dataset.day = dayStr;
            const totalQ = (dailyStat[dayStr].total_queries || 0);
            const secs   = Math.round((dailyStat[dayStr].cumulated_time || 0) / 1000);
            cell.title = dayStr + '  ·  ' + totalQ + ' queries  ·  ' + secs + 's';
            cell.addEventListener('click', () => AIQO.Sidebar.navigateToDay(dayStr));
          }
          cellsWrap.appendChild(cell);
        }

        row.appendChild(cellsWrap);
        container.appendChild(row);
      }

      // Legend cells
      if (legendContainer) {
        [0.2, 0.45, 0.7, 0.95].forEach((level) => {
          const c     = document.createElement('div');
          c.className = 'aiqo-heatmap-legend-cell';
          const alpha = Math.round(level * 255).toString(16).padStart(2, '0');
          c.style.backgroundColor = '#3b82f6' + alpha;
          legendContainer.appendChild(c);
        });
      }

      // Mark current day if set
      if (this._currentDay) {
        const sel = container.querySelector('.aiqo-heatmap-cell[data-day="' + this._currentDay + '"]');
        if (sel) sel.classList.add('selected');
      }
    },

    // ── Tree navigation ─────────────────────────────────────────────────────

    _bindTreeNavigation() {
      document.querySelectorAll('.aiqo-tree-year-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const yearEl = btn.closest('.aiqo-tree-year');
          if (yearEl) {
            const isExpanded = yearEl.classList.toggle('expanded');
            btn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
          }
        });
      });

      document.querySelectorAll('.aiqo-tree-month-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const monthEl = btn.closest('.aiqo-tree-month');
          if (monthEl) {
            const isExpanded = monthEl.classList.toggle('expanded');
            btn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
          }
        });
      });

      document.querySelectorAll('.aiqo-tree-day-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const day = btn.dataset.day;
          if (day) this.navigateToDay(day);
        });
      });
    },

    // ── View switching ──────────────────────────────────────────────────────

    _bindViewToggles() {
      const btnQuery   = document.getElementById('btn-section-query');
      const btnSummary = document.getElementById('btn-section-summary');
      const btnContext = document.getElementById('btn-section-context');

      if (btnQuery) {
        btnQuery.addEventListener('click', () => {
          const defaultDay = this._getDefaultDay();
          if (this._currentView === 'days') {
            if (!this._currentDay && defaultDay) this.navigateToDay(defaultDay);
          } else {
            if (defaultDay) this.navigateToDay(defaultDay);
            else this._showView('days');
          }
        });
      }

      if (btnSummary) {
        btnSummary.addEventListener('click', () => this._showView('summary'));
      }

      if (btnContext) {
        btnContext.addEventListener('click', () => this._showView('context'));
      }
    },

    _showView(view) {
      const daysEl    = document.getElementById('aiqo-view-days');
      const summaryEl = document.getElementById('aiqo-view-summary');
      const contextEl = document.getElementById('aiqo-view-context');

      const querySectionEl   = document.getElementById('aiqo-sidebar-section-query');
      const summarySectionEl = document.getElementById('aiqo-sidebar-section-summary');
      const contextSectionEl = document.getElementById('aiqo-sidebar-section-context');

      // Hide all main views and sidebar sections
      [daysEl, summaryEl, contextEl].forEach((el) => {
        if (el) el.classList.add('d-none');
      });
      [querySectionEl, summarySectionEl, contextSectionEl].forEach((el) => {
        if (el) el.classList.add('d-none');
      });

      // Reset all top-level nav tab states
      ['btn-section-query', 'btn-section-summary', 'btn-section-context'].forEach((id) => {
        const btn = document.getElementById(id);
        if (btn) { btn.classList.remove('active'); btn.setAttribute('aria-selected', 'false'); }
      });

      this._currentView = view;

      if (view === 'summary') {
        if (summaryEl) summaryEl.classList.remove('d-none');
        if (summarySectionEl) summarySectionEl.classList.remove('d-none');
        const btn = document.getElementById('btn-section-summary');
        if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); }
        this._activateFirstPanel('summary');
        if (AIQO.Components && AIQO.Components.GlobalSynthesis) {
          AIQO.Components.GlobalSynthesis.init();
        }
      } else if (view === 'context') {
        if (contextEl) contextEl.classList.remove('d-none');
        if (contextSectionEl) contextSectionEl.classList.remove('d-none');
        const btn = document.getElementById('btn-section-context');
        if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); }
        this._activateFirstPanel('context');
      } else {
        // 'days' (default)
        if (daysEl) daysEl.classList.remove('d-none');
        if (querySectionEl) querySectionEl.classList.remove('d-none');
        const btn = document.getElementById('btn-section-query');
        if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); }
      }
    },

    // ── Section panel navigation (Summary / Context) ────────────────────────

    _bindSectionNavItems() {
      document.querySelectorAll('.aiqo-section-nav-btn').forEach((btn) => {
        btn.addEventListener('click', () => this._activatePanelBtn(btn));
      });
    },

    _activateFirstPanel(sectionId) {
      const section = document.getElementById('aiqo-sidebar-section-' + sectionId);
      if (!section) return;
      // Restore last active panel; fall back to first button
      const activeBtn = section.querySelector('.aiqo-section-nav-btn.active')
                     || section.querySelector('.aiqo-section-nav-btn');
      if (activeBtn) this._activatePanelBtn(activeBtn);
    },

    _activatePanelBtn(btn) {
      const panelId = btn.dataset.panel;
      if (!panelId) return;
      // Derive section name from panel id prefix (e.g. "summary-panel-…" → "summary")
      const sectionId = panelId.split('-panel-')[0];
      const viewEl    = document.getElementById('aiqo-view-' + sectionId);
      if (!viewEl) return;
      // Hide all panels in this view, show target
      viewEl.querySelectorAll('.aiqo-section-panel').forEach((p) => p.classList.add('d-none'));
      const panel = document.getElementById(panelId);
      if (panel) panel.classList.remove('d-none');
      // Update sidebar nav active state
      const sectionEl = document.getElementById('aiqo-sidebar-section-' + sectionId);
      if (sectionEl) {
        sectionEl.querySelectorAll('.aiqo-section-nav-btn').forEach((b) => b.classList.remove('active'));
      }
      btn.classList.add('active');
    },

    // ── Initial activation ──────────────────────────────────────────────────

    getCurrentDay() {
      return this._currentDay;
    },

    _getDefaultDay() {
      if (this._currentDay) return this._currentDay;

      const allDays = (reportData.date_hierarchy || {}).all_days || [];
      const dailyStat = (reportData.statistics || {}).daily_stats || {};
      for (let i = allDays.length - 1; i >= 0; i--) {
        if (dailyStat[allDays[i]]) return allDays[i];
      }

      const firstPanel = document.querySelector('.aiqo-day-panel');
      return firstPanel ? firstPanel.dataset.day : null;
    },

    _openOnlyDayBranch(day) {
      document.querySelectorAll('.aiqo-tree-month.expanded, .aiqo-tree-year.expanded').forEach((el) => {
        el.classList.remove('expanded');
        const toggle = el.querySelector(':scope > button[aria-expanded]');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      });

      const btn = document.querySelector('.aiqo-tree-day-btn[data-day="' + day + '"]');
      if (!btn) return;

      const monthEl = btn.closest('.aiqo-tree-month');
      const yearEl  = btn.closest('.aiqo-tree-year');

      if (monthEl) {
        monthEl.classList.add('expanded');
        const monthBtn = monthEl.querySelector(':scope > .aiqo-tree-month-btn');
        if (monthBtn) monthBtn.setAttribute('aria-expanded', 'true');
      }
      if (yearEl) {
        yearEl.classList.add('expanded');
        const yearBtn = yearEl.querySelector(':scope > .aiqo-tree-year-btn');
        if (yearBtn) yearBtn.setAttribute('aria-expanded', 'true');
      }
    },

    _activateInitialDay() {
      const defaultDay = this._getDefaultDay();
      if (defaultDay) this.navigateToDay(defaultDay);
    },
  };
})();
