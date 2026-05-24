/**
 * Day timeline: Chart.js horizontal floating-bar chart with real time axis.
 * Only timed reports (query_start_utc + query_end_utc present) are rendered as bars.
 * Untimed reports are still accessible via the right detail pane.
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  const ROW_HEIGHT    = 34;   // px per query row in the chart
  const MIN_HEIGHT    = 120;  // minimum chart height (px)
  const CHART_PADDING = 56;   // top + bottom axes padding (px)
  const AXIS_PADDING_RATIO = 0.04;  // 4% padding on each side of the time range

  function durationColor(ms) {
    if (ms < 100)  return 'rgba(16, 185, 129, 0.80)';   // green
    if (ms < 500)  return 'rgba(234, 179, 8,  0.80)';   // yellow
    if (ms < 2000) return 'rgba(249, 115, 22, 0.80)';   // orange
    return           'rgba(239, 68,  68,  0.80)';        // red
  }

  function durationBorder(ms) {
    if (ms < 100)  return 'rgba(16, 185, 129, 1)';
    if (ms < 500)  return 'rgba(234, 179, 8,  1)';
    if (ms < 2000) return 'rgba(249, 115, 22, 1)';
    return           'rgba(239, 68,  68,  1)';
  }

  let _copyToastTimer = null;

  function showCopyToast(code) {
    const toast = document.getElementById('aiqo-copy-toast');
    const msg   = document.getElementById('aiqo-copy-toast-msg');
    if (!toast) return;
    if (msg) msg.textContent = '‘' + code + '’ copied';
    toast.classList.add('visible');
    if (_copyToastTimer) clearTimeout(_copyToastTimer);
    _copyToastTimer = setTimeout(() => toast.classList.remove('visible'), 2200);
  }

  AIQO.Components.DayTimeline = {
    _charts: {},
    _selectedChartIdx: {},
    _originalToChart: {},

    initForDay(day) {
      if (!day) return;
      const safeDay = ReportUtils.dateToSafeId(day);
      if (this._charts[safeDay]) return; // already initialized

      const allReports = (reportData.reports.by_day[day] || []);

      // Only render reports that have valid timing data in the chart.
      // Untimed reports remain accessible in the right-pane details.
      const timedReports = allReports
        .map((r, originalIdx) => ({ r, originalIdx }))
        .filter(({ r }) => r.query_start_utc != null && r.query_end_utc != null)
        .sort((a, b) => a.r.query_start_utc - b.r.query_start_utc);

      const canvas  = document.getElementById('timeline-' + safeDay);
      const wrapper = document.getElementById('timeline-wrapper-' + safeDay);
      if (!canvas || !wrapper) return;

      if (!timedReports.length) {
        wrapper.innerHTML = '<p class="text-muted small p-2 m-0">No timing data available for this day.</p>';
        this._charts[safeDay] = null;
        return;
      }

      // Build reverse map: originalIdx → chartIdx (for external highlight calls)
      const origToChart = {};
      timedReports.forEach(({ originalIdx }, chartIdx) => {
        origToChart[originalIdx] = chartIdx;
      });
      this._originalToChart[safeDay] = origToChart;
      this._selectedChartIdx[safeDay] = origToChart[0] != null ? origToChart[0] : 0;

      // Chart data — only timed entries, no nulls
      const labels       = timedReports.map(({ r }) => {
        const code  = r.code ? r.code.substring(0, 6) : '??';
        const icons = [
          r.has_query_optimizations ? '⚡' : '',
          r.has_ai_hints            ? '»' : '',
        ].filter(Boolean).join('');
        return icons ? code + ' ' + icons : code;
      });

      const data = timedReports.map(({ r }) => {
        // Ensure a minimum 1-second bar so very fast queries are visible
        const end = Math.max(r.query_end_utc, r.query_start_utc + 1000);
        return [r.query_start_utc, end];
      });

      const sel0         = this._selectedChartIdx[safeDay];
      const bgColors     = timedReports.map(({ r }, i) => durationColor(r.duration || 0));
      const borderColors = timedReports.map(({ r }, i) =>
        i === sel0 ? '#1d4ed8' : durationBorder(r.duration || 0));
      const borderWidths = timedReports.map((_, i) => i === sel0 ? 3 : 1);

      // Compute explicit axis bounds so Chart.js never uses epoch as default
      const allStarts = timedReports.map(({ r }) => r.query_start_utc);
      const allEnds   = timedReports.map(({ r }) => r.query_end_utc);
      const minTs     = Math.min(...allStarts);
      const maxTs     = Math.max(...allEnds);
      const span      = Math.max(maxTs - minTs, 1000);          // at least 1s span
      const pad       = Math.max(span * AXIS_PADDING_RATIO, 5000); // at least 5s padding
      const xMin      = minTs - pad;
      const xMax      = maxTs + pad;

      // Set wrapper height proportional to number of rows
      const chartHeight = Math.max(MIN_HEIGHT, timedReports.length * ROW_HEIGHT + CHART_PADDING);
      wrapper.style.height = chartHeight + 'px';

      // Destroy any stale chart on this canvas
      const stale = Chart.getChart(canvas);
      if (stale) stale.destroy();

      const chart = new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            data,
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: borderWidths,
            borderRadius: 3,
            borderSkipped: false,
            minBarLength: 4,
          }],
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          onHover(event) {
            if (event.native) event.native.target.style.cursor = 'pointer';
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title(items) {
                  const { r } = timedReports[items[0].dataIndex];
                  return (r.title || labels[items[0].dataIndex]).substring(0, 70);
                },
                label(ctx) {
                  const { r } = timedReports[ctx.dataIndex];
                  const dur      = r.duration != null
                    ? Duration.fromMillis(r.duration).toFormat("m'm' s.SSS's'")
                    : 'n/a';
                  const startFmt = luxon.DateTime.fromMillis(r.query_start_utc, { zone: 'utc' })
                    .toFormat('HH:mm:ss');
                  return dur + '  @' + startFmt;
                },
              },
            },
          },
          scales: {
            x: {
              type:     'time',
              min:      xMin,
              max:      xMax,
              adapters: { date: { zone: 'utc' } },
              time: {
                displayFormats: {
                  millisecond: 'HH:mm:ss.SSS',
                  second:      'HH:mm:ss',
                  minute:      'HH:mm',
                  hour:        'HH:mm',
                },
              },
              ticks: { font: { size: 10 }, color: '#64748b', maxRotation: 0 },
              grid:  { color: 'rgba(148, 163, 184, 0.15)' },
            },
            y: {
              ticks: {
                font:  { family: 'monospace', size: 11 },
                color: '#475569',
              },
              grid: { color: 'rgba(148, 163, 184, 0.1)' },
            },
          },
          onClick(event, elements, chartInstance) {
            let chartIdx;
            if (elements.length > 0) {
              chartIdx = elements[0].dataIndex;
            } else {
              // Click outside a bar (e.g. on Y-axis label): detect row from Y position
              const yScale = chartInstance && chartInstance.scales && chartInstance.scales.y;
              if (!yScale || event.native == null) return;
              const rawIdx = Math.round(yScale.getValueForPixel(event.native.offsetY));
              if (rawIdx == null || rawIdx < 0 || rawIdx >= timedReports.length) return;
              chartIdx = rawIdx;
            }
            const originalIdx = timedReports[chartIdx].originalIdx;
            AIQO.Components.DayTimeline._selectedChartIdx[safeDay] = chartIdx;
            AIQO.Components.DayTimeline._updateSelection(safeDay);
            const panel = document.getElementById('day-panel-' + safeDay);
            if (panel && originalIdx >= 0) {
              AIQO.Components.Tabs._activateQueryByIndex(panel, originalIdx);
            }
          },
        },
      });

      // Store original border colors for _updateSelection reference
      chart._aiqoBorderColors = timedReports.map(({ r }) => durationBorder(r.duration || 0));

      this._charts[safeDay] = chart;

      // Double-click on a row copies its short code to the clipboard
      canvas.addEventListener('dblclick', (event) => {
        const yScale = chart.scales && chart.scales.y;
        if (!yScale) return;
        const rawIdx = Math.round(yScale.getValueForPixel(event.offsetY));
        if (rawIdx == null || rawIdx < 0 || rawIdx >= timedReports.length) return;
        const code = timedReports[rawIdx].r.code
          ? timedReports[rawIdx].r.code.substring(0, 6)
          : labels[rawIdx];
        navigator.clipboard.writeText(code).then(() => showCopyToast(code)).catch(() => {
          // fallback for browsers that deny clipboard outside user gesture
          showCopyToast(code);
        });
      });

      // Hint note at the bottom of the timeline pane
      const pane = canvas.closest('.aiqo-timeline-pane');
      if (pane && !pane.querySelector('.aiqo-timeline-hint')) {
        const hint = document.createElement('div');
        hint.className = 'aiqo-timeline-hint';
        hint.textContent = 'Double click to copy query code';
        pane.appendChild(hint);
      }
    },

    _updateSelection(safeDay) {
      const chart = this._charts[safeDay];
      if (!chart) return;
      const selected = this._selectedChartIdx[safeDay];
      const ds = chart.data.datasets[0];
      ds.borderColor = ds.data.map((_, i) => {
        if (i === selected) return '#1d4ed8';
        // retrieve original borderColor from bgColors: use durationBorder via chart label lookup
        return chart._aiqoBorderColors[i];
      });
      ds.borderWidth = ds.data.map((_, i) => i === selected ? 3 : 1);
      chart.update('none');
    },

    highlightBar(safeDay, originalIdx) {
      const chartIdx = (this._originalToChart[safeDay] || {})[originalIdx];
      if (chartIdx === undefined) return;
      this._selectedChartIdx[safeDay] = chartIdx;
      this._updateSelection(safeDay);
    },

    destroyForDay(day) {
      const safeDay = ReportUtils.dateToSafeId(day);
      const ch = this._charts[safeDay];
      if (ch) { ch.destroy(); delete this._charts[safeDay]; }
      delete this._charts[safeDay];
    },
  };

})();
