/**
 * Tabs component logic (year/month/day containers and query tab UX)
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  AIQO.Components.Tabs = {
    init() {
      this._renderQueryGantts();
      this._bindQueryGanttSelection();
      this._bindDuplicateAnalysisLinks();

      // Initialize Split.js two-pane layout for all day containers
      document.querySelectorAll('[id^="split-container-"]').forEach((container) => {
        const leftPane = container.querySelector('.split:nth-child(1)');
        const rightPane = container.querySelector('.split:nth-child(2)');
        if (!leftPane || !rightPane || typeof Split !== 'function') return;
        try {
          Split([leftPane, rightPane], {
            sizes: [30, 70],
            minSize: [150, 300],
            gutterSize: 6,
            cursor: 'col-resize',
            gutter: function (index, direction) {
              const gutter = document.createElement('div');
              gutter.className = 'gutter gutter-' + direction;
              gutter.style.background = '#ddd';
              gutter.style.cursor = 'col-resize';
              gutter.style.width = '6px';
              return gutter;
            },
          });
        } catch (e) {
          console.warn('Split init failed for container', container.id, e);
        }
      });

      // Year tab change: show corresponding month container and activate last month
      document.querySelectorAll('[id^="tab-year-"]').forEach((yearTab) => {
        yearTab.addEventListener('shown.bs.tab', function (e) {
          const m = e.target.id.match(/tab-year-(\d+)-tab/);
          if (!m) return;
          const year = m[1];

          // Hide all month containers, then show the selected year
          document
            .querySelectorAll('.month-tabs-container')
            .forEach((el) => el.classList.add('d-none'));
          const monthContainer = document.getElementById(
            `month-tabs-container-${year}`
          );
          if (monthContainer) {
            monthContainer.classList.remove('d-none');
            // Activate last (most recent) month tab
            const monthTabs = monthContainer.querySelectorAll('.nav-link');
            if (monthTabs.length > 0) {
              const lastMonthTab = monthTabs[monthTabs.length - 1];
              bootstrap.Tab.getOrCreateInstance(lastMonthTab).show();
            }
          }
        });
      });

      // Month tab change: show corresponding day container/content and activate last day
      document.querySelectorAll('[id^="tab-month-"]').forEach((monthTab) => {
        monthTab.addEventListener('shown.bs.tab', function (e) {
          const m = e.target.id.match(/tab-month-(.+)-tab/);
          if (!m) return;
          const yearMonth = m[1];

          // Hide all day containers, then show the selected month
          document
            .querySelectorAll('.day-tabs-container')
            .forEach((el) => el.classList.add('d-none'));
          const dayContainer = document.getElementById(
            `day-tabs-container-${yearMonth}`
          );
          if (dayContainer) {
            dayContainer.classList.remove('d-none');
            // Activate last (most recent) day tab
            const dayTabs = dayContainer.querySelectorAll('.nav-link');
            if (dayTabs.length > 0) {
              const lastDayTab = dayTabs[dayTabs.length - 1];
              bootstrap.Tab.getOrCreateInstance(lastDayTab).show();
            }
          }

          // Hide all day tab contents, then show selected month content
          document
            .querySelectorAll('.day-tab-content')
            .forEach((el) => el.classList.add('d-none'));
          const dayTabContent = document.getElementById(
            `dayTabContent-${yearMonth}`
          );
          if (dayTabContent) {
            dayTabContent.classList.remove('d-none');
          }
        });
      });

      // Double-click on a gantt row -> copy short code to clipboard
      document.querySelectorAll('.query-gantt-row').forEach((btn) => {
        btn.addEventListener('dblclick', function () {
          const fullCode = this.dataset.queryCode;
          if (!fullCode) return;
          const shortCode = fullCode.substring(0, 6);
          navigator.clipboard
            .writeText(shortCode)
            .then(() => {
              const toast = document.createElement('div');
              toast.className =
                'alert alert-success position-fixed top-0 end-0 m-3 py-2 px-3 shadow';
              toast.textContent = `Codice corto "${shortCode}" copiato negli appunti!`;
              document.body.appendChild(toast);
              setTimeout(() => toast.remove(), 2000);
            })
            .catch((err) => console.error('Clipboard error:', err));
        });
      });

      window.addEventListener('resize', () => this._renderQueryGantts());
    },

    _bindQueryGanttSelection() {
      document.querySelectorAll('.query-gantt-row').forEach((row) => {
        row.addEventListener('click', (event) => {
          event.preventDefault();
          this._activateQueryRow(row);
        });
      });
    },

    _bindDuplicateAnalysisLinks() {
      document.querySelectorAll('[data-role="duplicate-ai-analysis-link"]').forEach((link) => {
        link.addEventListener('click', (event) => {
          event.preventDefault();

          const targetDay = link.getAttribute('data-target-day');
          const targetIndex = link.getAttribute('data-target-index');
          if (!targetDay || targetIndex === null) return;

          const targetRow = document.getElementById(`query-tab-${targetDay}-${targetIndex}`);
          if (!targetRow) return;

          this._activateQueryRow(targetRow);
          targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      });
    },

    _activateQueryRow(row) {
      if (!row) return;

      const dayPane = row.closest('[id^="tab-day-"]');
      const targetSelector = row.getAttribute('data-query-target');
      if (!dayPane || !targetSelector) return;

      const targetPane = dayPane.querySelector(targetSelector);
      if (!targetPane) return;

      dayPane.querySelectorAll('.query-gantt-row.active').forEach((activeRow) => {
        activeRow.classList.remove('active');
        activeRow.setAttribute('aria-selected', 'false');
      });

      dayPane.querySelectorAll('.query-tab-content .tab-pane.show.active').forEach((activePane) => {
        activePane.classList.remove('show', 'active');
      });

      row.classList.add('active');
      row.setAttribute('aria-selected', 'true');
      targetPane.classList.add('show', 'active');

      row.dispatchEvent(new Event('shown.bs.tab', { bubbles: true }));
    },

    _renderQueryGantts() {
      document.querySelectorAll('.query-gantt-panel').forEach((panel) => {
        const rows = Array.from(panel.querySelectorAll('.query-gantt-row'));
        if (!rows.length) return;

        const validRows = rows
          .map((row) => {
            const startUtc = Number(row.dataset.startUtc);
            const endUtc = Number(row.dataset.endUtc);
            return Number.isFinite(startUtc) && Number.isFinite(endUtc) && endUtc >= startUtc
              ? { row, startUtc, endUtc }
              : null;
          })
          .filter(Boolean);

        const startLabel = panel.querySelector('[data-role="gantt-scale-start"]');
        const midLabel = panel.querySelector('[data-role="gantt-scale-mid"]');
        const endLabel = panel.querySelector('[data-role="gantt-scale-end"]');

        if (!validRows.length) {
          if (startLabel) startLabel.textContent = '--:--:--';
          if (midLabel) midLabel.textContent = '--:--:--';
          if (endLabel) endLabel.textContent = '--:--:--';
          rows.forEach((row) => {
            const bar = row.querySelector('.query-gantt-bar');
            if (bar) bar.style.display = 'none';
          });
          return;
        }

        const minStart = Math.min(...validRows.map((item) => item.startUtc));
        const maxEnd = Math.max(...validRows.map((item) => item.endUtc));
        const span = Math.max(maxEnd - minStart, 1);
        const midPoint = minStart + span / 2;

        if (startLabel) startLabel.textContent = this._formatGanttTime(minStart);
        if (midLabel) midLabel.textContent = this._formatGanttTime(midPoint);
        if (endLabel) endLabel.textContent = this._formatGanttEndTime(minStart, maxEnd);

        validRows.forEach(({ row, startUtc, endUtc }) => {
          const bar = row.querySelector('.query-gantt-bar');
          if (!bar) return;

          const leftPct = ((startUtc - minStart) / span) * 100;
          const widthPct = Math.max(((endUtc - startUtc) / span) * 100, 0.8);
          const queryTitle = row.dataset.queryTitle || row.dataset.queryCode || 'N/A';

          bar.style.display = 'block';
          bar.style.left = `${Math.min(Math.max(leftPct, 0), 100)}%`;
          bar.style.width = `${Math.min(widthPct, 100)}%`;
          row.removeAttribute('title');
          row.setAttribute('data-bs-title', queryTitle);

          const existingTooltip = bootstrap.Tooltip.getInstance(row);
          if (existingTooltip) {
            existingTooltip.dispose();
          }
          bootstrap.Tooltip.getOrCreateInstance(row, {
            container: 'body',
            trigger: 'hover focus',
          });
        });
      });
    },

    _formatGanttTime(value) {
      const dt = luxon.DateTime.fromMillis(value, { zone: 'utc' });
      return dt.isValid ? dt.toFormat('HH:mm') : '--:--';
    },

    _formatGanttEndTime(startValue, endValue) {
      const start = luxon.DateTime.fromMillis(startValue, { zone: 'utc' });
      const end = luxon.DateTime.fromMillis(endValue, { zone: 'utc' });
      if (!start.isValid || !end.isValid) return '--:--:--';

      const dayOffset = Math.floor(end.startOf('day').diff(start.startOf('day'), 'days').days);
      return dayOffset > 0 ? `${end.toFormat('HH:mm')} (+${dayOffset})` : end.toFormat('HH:mm');
    },
  };
})();
