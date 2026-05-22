/**
 * Chart factory for creating different types of charts
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  const BYTES_PER_BUFFER_BLOCK = 8192;
  const BUFFER_KEYS_FOR_TOTAL_IO = ['shared_read', 'shared_dirtied', 'shared_written', 'temp_read', 'temp_written'];
  const QUERY_POINT_HOVER_RADIUS_PX = 12;

  AIQO.Core.ChartFactory = class ChartFactory {
  constructor(reportData) {
    this.reportData = reportData;
    this.annotationService = new AIQO.Core.AnnotationService(reportData);
  }

  _applyDatasetVisibilityState(datasets, visibilityState) {
    return datasets.map((dataset) => {
      const defaultVisible = dataset.hidden !== true;
      const storedVisible =
        visibilityState && Object.prototype.hasOwnProperty.call(visibilityState, dataset.label)
          ? visibilityState[dataset.label]
          : defaultVisible;
      return Object.assign({}, dataset, {
        hidden: !storedVisible,
      });
    });
  }

  _collectDatasetVisibility(chart) {
    const visibilityState = {};
    (chart.data.datasets || []).forEach((dataset, datasetIndex) => {
      if (!dataset || !dataset.label) return;
      visibilityState[dataset.label] = typeof chart.isDatasetVisible === 'function'
        ? chart.isDatasetVisible(datasetIndex)
        : !dataset.hidden;
    });
    return visibilityState;
  }

  _getDatasetColor(dataset) {
    if (!dataset) return null;
    if (dataset.label === 'Execution Time (hours)') return '#000000';
    if (Array.isArray(dataset.borderColor)) return dataset.borderColor[0] || null;
    return dataset.borderColor || null;
  }

  _getVisibleDatasetsForScale(chart, scaleId) {
    return (chart.data.datasets || []).filter((dataset, datasetIndex) => {
      if (!dataset || dataset.yAxisID !== scaleId) return false;
      return typeof chart.isDatasetVisible === 'function'
        ? chart.isDatasetVisible(datasetIndex)
        : !dataset.hidden;
    });
  }

  _applyAxisColors(chart) {
    if (!chart || !chart.options || !chart.options.scales) return;

    Object.entries(chart.options.scales).forEach(([scaleId, scale]) => {
      if (scaleId === 'x' || !scale) return;

      const matchingDataset = this._getVisibleDatasetsForScale(chart, scaleId)[0];

      const axisColor = this._getDatasetColor(matchingDataset);
      if (!axisColor) return;

      if (!scale.ticks) scale.ticks = {};
      if (!scale.title) scale.title = {};
      if (!scale.border) scale.border = {};
      scale.ticks.color = axisColor;
      scale.title.color = axisColor;
      scale.border.color = axisColor;
    });
  }

  _applyAxisTitles(chart) {
    if (!chart || !chart.options || !chart.options.scales) return;

    Object.entries(chart.options.scales).forEach(([scaleId, scale]) => {
      if (scaleId === 'x' || !scale || !scale.title) return;

      const visibleDatasets = this._getVisibleDatasetsForScale(chart, scaleId);
      if (visibleDatasets.length === 0) return;

      const visibleLabels = visibleDatasets
        .map((dataset) => dataset && dataset.label)
        .filter(Boolean);
      if (visibleLabels.length === 0) return;

      const titleText = visibleLabels.length === 1
        ? visibleLabels[0]
        : visibleLabels.join(' / ');

      scale.title.text = titleText;
    });
  }

  _isAxisVisible(chart, scaleId) {
    return (chart.data.datasets || []).some((dataset, datasetIndex) => {
      if (!dataset || dataset.yAxisID !== scaleId) return false;
      return typeof chart.isDatasetVisible === 'function'
        ? chart.isDatasetVisible(datasetIndex)
        : !dataset.hidden;
    });
  }

  _syncAxisVisibility(chart) {
    if (!chart || !chart.options || !chart.options.scales) return;

    ['yAxisRightTotalQueries', 'yCost', 'yRows', 'yBuffer', 'yWAL'].forEach((scaleId) => {
      if (!chart.options.scales[scaleId]) return;
      chart.options.scales[scaleId].display = this._isAxisVisible(chart, scaleId);
    });
  }

  _applyAxisState(chart) {
    this._syncAxisVisibility(chart);
    this._applyAxisTitles(chart);
    this._applyAxisColors(chart);
  }

  createDailyCumulatedTimeChart(ctx, visibilityState, onVisibilityChange) {
    try {
      const chartData = AIQO.Core.DataValidator.validateChartData(this.reportData.charts.daily_trends);
      const annotations = this.annotationService.buildDailyAnnotations();
      const chart = new Chart(ctx, {
        type: 'line',
        data: this._createDailyChartData(chartData, visibilityState),
        options: this._createDailyChartOptions(annotations, onVisibilityChange),
      });
      this._applyAxisState(chart);
      chart.update('none');
      return chart;
    } catch (error) {
      console.error('Failed to create daily chart:', error);
      return null;
    }
  }

  createQueryExecutionChart(ctx, canvasId, queryCode, allExecutions, selectedDay, visibilityState, onVisibilityChange) {
    try {
      const validExecutions = AIQO.Core.DataValidator.validateExecutionData(allExecutions);
      const processedData = this._processExecutionData(validExecutions);
      const annotations = this.annotationService.buildQueryAnnotations(queryCode, processedData.labels, selectedDay);
      const chart = new Chart(ctx, {
        type: 'line',
        data: this._createQueryChartData(processedData, visibilityState),
        options: this._createQueryChartOptions(selectedDay, annotations, onVisibilityChange),
      });
      this._applyAxisState(chart);
      chart.update('none');
      return chart;
    } catch (error) {
      console.error('Failed to create query execution chart:', error);
      return null;
    }
  }

  _createDailyChartData(chartData, visibilityState) {
    const datasets = [
      {
        label: 'Total Cumulated Time',
        data: chartData.cumulated_time,
        borderColor: 'rgba(92, 176, 171, 1)',
        backgroundColor: 'rgba(92, 176, 171, 0.3)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        spanGaps: true,
        yAxisID: 'y',
      },
      {
        label: 'Total Queries Count',
        data: chartData.total_queries,
        type: 'bar',
        backgroundColor: 'rgba(166, 146, 222, 0.55)',
        borderColor: 'rgba(166, 146, 222, 1)',
        borderWidth: 1,
        yAxisID: 'yAxisRightTotalQueries',
        hidden: true,
      },
    ];

    return {
      labels: chartData.labels,
      datasets: this._applyDatasetVisibilityState(datasets, visibilityState),
    };
  }

  _createDailyChartOptions(annotations, onVisibilityChange) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          onClick: (e, legendItem, legend) => {
            const chart = legend.chart;
            Chart.defaults.plugins.legend.onClick.call(this, e, legendItem, legend);
            if (typeof onVisibilityChange === 'function') {
              onVisibilityChange(this._collectDatasetVisibility(chart));
            }
            this._applyAxisState(chart);
            chart.update();
          },
        },
        title: { display: true, text: 'Daily Cumulated Time and Query Count Trends' },
        tooltip: {
          callbacks: {
            label: function (context) {
              let label = context.dataset.label || '';
              if (label) label += ': ';
              if (context.parsed.y !== null) {
                if (context.dataset.yAxisID === 'yAxisRightTotalQueries') {
                  label += context.parsed.y.toFixed(0);
                } else {
                  label += context.parsed.y.toFixed(2) + ' min';
                }
              }
              return label;
            },
          },
        },
        annotation: { annotations },
      },
      scales: {
        x: {
          type: 'time',
          time: {
            unit: 'day',
            tooltipFormat: 'yyyy-LL-dd',
            displayFormats: { day: 'yyyy-LL-dd' }
          },
          title: { display: true, text: 'Date' }
        },
        y: AIQO.Core.ScaleHelper.createCumulatedTimeScale(),
        yAxisRightTotalQueries: Object.assign(AIQO.Core.ScaleHelper.createQueryCountScale(), { display: false }),
      },
    };
  }

  _processExecutionData(executions) {
    executions.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

    const normalizeNumber = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);
    const bufferToBytes = (execution, key) => {
      if (!execution) return null;
      const precomputed = normalizeNumber(execution.buffers_bytes?.[key]);
      if (precomputed !== null) return precomputed;
      const rawBlocks = normalizeNumber(execution.buffers?.[key]);
      return rawBlocks !== null ? rawBlocks * BYTES_PER_BUFFER_BLOCK : null;
    };
    const computeTotalIo = (execution) => {
      const precomputed = normalizeNumber(execution?.total_io_bytes);
      if (precomputed !== null) return precomputed;
      const components = BUFFER_KEYS_FOR_TOTAL_IO.map((key) => bufferToBytes(execution, key)).filter((v) => v !== null);
      const walBytes = normalizeNumber(execution?.wal?.bytes);
      if (walBytes !== null) components.push(walBytes);
      if (components.length === 0) return null;
      return components.reduce((sum, v) => sum + v, 0);
    };

    return {
      labels: executions.map((e) => e.timestamp.split(' ')[0]),
      durations: executions.map((e) => (e.duration !== null ? e.duration / 3600000 : null)),
      costs: executions.map((e) => ReportUtils.parseCostValue(e.cost)),
      rows: executions.map((e) => ReportUtils.parseRowsValue(e.rows)),
      buffers: {
        shared_hit: executions.map((e) => e.buffers?.shared_hit ?? null),
        shared_read: executions.map((e) => e.buffers?.shared_read ?? null),
        shared_dirtied: executions.map((e) => e.buffers?.shared_dirtied ?? null),
        shared_written: executions.map((e) => e.buffers?.shared_written ?? null),
        temp_read: executions.map((e) => e.buffers?.temp_read ?? null),
        temp_written: executions.map((e) => e.buffers?.temp_written ?? null),
      },
      wal: {
        records: executions.map((e) => e.wal?.records ?? null),
        fpi: executions.map((e) => e.wal?.fpi ?? null),
        bytes: executions.map((e) => e.wal?.bytes ?? null),
      },
      io_total: executions.map((e) => computeTotalIo(e)),
    };
  }

  _createQueryChartData(processedData, visibilityState) {
    const datasets = [
      {
        label: 'Execution Time (hours)',
        data: processedData.durations,
        borderColor: '#000000',
        backgroundColor: 'rgba(0, 0, 0, 0.2)',
        pointBackgroundColor: '#000000',
        pointBorderColor: '#000000',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 3,
        yAxisID: 'y',
      },
      {
        label: 'Cost',
        data: processedData.costs,
        borderColor: 'rgba(223, 166, 107, 1)',
        backgroundColor: 'rgba(223, 166, 107, 0.28)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 3,
        yAxisID: 'yCost',
        hidden: true,
      },
      {
        label: 'Rows',
        data: processedData.rows,
        borderColor: 'rgba(106, 168, 214, 1)',
        backgroundColor: 'rgba(106, 168, 214, 0.28)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 3,
        yAxisID: 'yRows',
        hidden: true,
      },
    ];

    if (processedData.buffers) {
      const bufferColors = {
        shared_hit: 'rgba(161, 135, 211, 1)',
        shared_read: 'rgba(217, 132, 156, 1)',
        shared_dirtied: 'rgba(224, 198, 112, 1)',
        shared_written: 'rgba(109, 182, 132, 1)',
        temp_read: 'rgba(122, 178, 216, 1)',
        temp_written: 'rgba(223, 164, 118, 1)',
      };
      Object.entries(processedData.buffers).forEach(([key, data]) => {
        if (data.some((v) => v !== null)) {
          datasets.push({
            label: `Buffer ${key.replace('_', ' ')}`,
            data: data,
            borderColor: bufferColors[key],
            backgroundColor: bufferColors[key].replace('1)', '0.2)'),
            borderWidth: 2,
            fill: false,
            tension: 0.1,
            spanGaps: true,
            pointRadius: 2,
            yAxisID: 'yBuffer',
            hidden: true,
          });
        }
      });
    }

    if (processedData.wal) {
      const walColors = {
        records: 'rgba(102, 156, 209, 1)',
        fpi: 'rgba(205, 123, 138, 1)',
        bytes: 'rgba(116, 179, 131, 1)',
      };
      Object.entries(processedData.wal).forEach(([key, data]) => {
        if (data.some((v) => v !== null)) {
          datasets.push({
            label: `WAL ${key}`,
            data: data,
            borderColor: walColors[key],
            backgroundColor: walColors[key].replace('1)', '0.2)'),
            borderWidth: 2,
            fill: false,
            tension: 0.1,
            spanGaps: true,
            pointRadius: 2,
            yAxisID: 'yWAL',
            hidden: true,
          });
        }
      });
    }

    if (processedData.io_total && processedData.io_total.some((v) => v !== null)) {
      datasets.push({
        label: 'I/O Total (shared read + dirtied + WAL bytes)',
        data: processedData.io_total,
        borderColor: 'rgba(98, 168, 168, 1)',
        backgroundColor: 'rgba(98, 168, 168, 0.28)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 2,
        yAxisID: 'yWAL',
        hidden: true,
      });
    }

    return {
      labels: processedData.labels,
      datasets: this._applyDatasetVisibilityState(datasets, visibilityState),
    };
  }

  _createQueryChartOptions(selectedDay, annotations, onVisibilityChange) {
    return {
      responsive: true,
      onHover: (event, activeElements, chart) => {
        const canvas = chart && chart.canvas ? chart.canvas : event && event.native ? event.native.target : null;
        if (!canvas) return;

        const hoveredElements = Array.isArray(activeElements) ? activeElements : [];
        if (hoveredElements.length > 0) {
          canvas.style.cursor = 'pointer';
          return;
        }

        const nativeEvent = event && event.native ? event.native : event;
        if (!nativeEvent || typeof chart.getElementsAtEventForMode !== 'function') {
          canvas.style.cursor = 'default';
          return;
        }

        const nearbyPoints = chart.getElementsAtEventForMode(
          nativeEvent,
          'nearest',
          { intersect: false },
          false
        );
        if (!nearbyPoints.length) {
          canvas.style.cursor = 'default';
          return;
        }

        const nearestPoint = nearbyPoints[0] && nearbyPoints[0].element ? nearbyPoints[0].element : null;
        if (!nearestPoint || typeof nearestPoint.x !== 'number' || typeof nearestPoint.y !== 'number') {
          canvas.style.cursor = 'default';
          return;
        }

        const eventX = typeof nativeEvent.offsetX === 'number' ? nativeEvent.offsetX : nativeEvent.x;
        const eventY = typeof nativeEvent.offsetY === 'number' ? nativeEvent.offsetY : nativeEvent.y;
        if (typeof eventX !== 'number' || typeof eventY !== 'number') {
          canvas.style.cursor = 'default';
          return;
        }

        const deltaX = nearestPoint.x - eventX;
        const deltaY = nearestPoint.y - eventY;
        const distance = Math.sqrt((deltaX * deltaX) + (deltaY * deltaY));
        canvas.style.cursor = distance <= QUERY_POINT_HOVER_RADIUS_PX ? 'pointer' : 'default';
      },
      plugins: {
        legend: {
          display: true,
          onClick: (e, legendItem, legend) => {
            const chart = legend.chart;
            Chart.defaults.plugins.legend.onClick.call(this, e, legendItem, legend);
            if (typeof onVisibilityChange === 'function') {
              onVisibilityChange(this._collectDatasetVisibility(chart));
            }
            this._applyAxisState(chart);
            chart.update();
          },
        },
        annotation: { annotations },
      },
      scales: {
        x: {
          type: 'time',
          time: {
            unit: 'day',
            tooltipFormat: 'yyyy-LL-dd',
            displayFormats: { day: 'yyyy-LL-dd' }
          },
          title: { display: true, text: 'Timestamp' },
          ticks: {
            autoSkip: true,
            maxTicksLimit: 10,
            font: (ctx) => {
              const lbl = ctx && ctx.tick && ctx.tick.label;
              if (lbl === selectedDay) return { weight: 'bold' };
              return {};
            },
            color: (ctx) => {
              const lbl = ctx && ctx.tick && ctx.tick.label;
              return lbl === selectedDay ? '#1d4ed8' : '#94a3b8';
            },
          },
        },
        y: AIQO.Core.ScaleHelper.createTimeScale(),
        yCost: AIQO.Core.ScaleHelper.createCostScale(),
        yRows: AIQO.Core.ScaleHelper.createRowsScale(),
        yBuffer: Object.assign(AIQO.Core.ScaleHelper.createBufferScale(), { display: false }),
        yWAL: Object.assign(AIQO.Core.ScaleHelper.createWALScale(), { display: false }),
      },
    };
  }
}

})();
