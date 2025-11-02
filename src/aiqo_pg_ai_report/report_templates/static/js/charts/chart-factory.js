/**
 * Chart factory for creating different types of charts
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  const BYTES_PER_BUFFER_BLOCK = 8192;
  const BUFFER_KEYS_FOR_TOTAL_IO = ['shared_read', 'shared_dirtied', 'shared_written', 'temp_read', 'temp_written'];

  AIQO.Core.ChartFactory = class ChartFactory {
  constructor(reportData) {
    this.reportData = reportData;
    this.annotationBuilder = new AIQO.Core.AnnotationBuilder(reportData);
  }

  createDailyCumulatedTimeChart(ctx) {
    try {
      const chartData = AIQO.Core.DataValidator.validateChartData(this.reportData.charts.daily_trends);
      const annotations = this.annotationBuilder.buildGenericAnnotations();
      return new Chart(ctx, {
        type: 'line',
        data: this._createDailyChartData(chartData),
        options: this._createDailyChartOptions(annotations),
      });
    } catch (error) {
      console.error('Failed to create daily chart:', error);
      return null;
    }
  }

  createQueryExecutionChart(ctx, canvasId, queryCode, allExecutions, selectedDay) {
    try {
      const validExecutions = AIQO.Core.DataValidator.validateExecutionData(allExecutions);
      const processedData = this._processExecutionData(validExecutions);
      const annotations = this.annotationBuilder.buildQueryAnnotations(canvasId, processedData.labels);
      return new Chart(ctx, {
        type: 'line',
        data: this._createQueryChartData(processedData),
        options: this._createQueryChartOptions(selectedDay, annotations),
      });
    } catch (error) {
      console.error('Failed to create query execution chart:', error);
      return null;
    }
  }

  _createDailyChartData(chartData) {
    return {
      labels: chartData.labels,
      datasets: [
        {
          label: 'Total Cumulated Time',
          data: chartData.cumulated_time,
          borderColor: 'rgb(75, 192, 192)',
          backgroundColor: 'rgb(75, 192, 192)',
          fill: false,
          tension: 0.1,
          spanGaps: true,
          yAxisID: 'y',
        },
        {
          label: 'Total Queries Count',
          data: chartData.total_queries,
          type: 'bar',
          backgroundColor: 'rgba(153, 102, 255, 0.5)',
          borderColor: 'rgba(153, 102, 255, 1)',
          borderWidth: 1,
          yAxisID: 'yAxisRightTotalQueries',
          hidden: true,
        },
      ],
    };
  }

  _createDailyChartOptions(annotations) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          onClick: (e, legendItem, legend) => {
            const chart = legend.chart;
            Chart.defaults.plugins.legend.onClick.call(this, e, legendItem, legend);
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (ds && ds.yAxisID === 'yAxisRightTotalQueries') {
              const isVisible = typeof chart.isDatasetVisible === 'function' ? chart.isDatasetVisible(legendItem.datasetIndex) : !ds.hidden;
              chart.options.scales.yAxisRightTotalQueries.display = isVisible;
              chart.update();
            }
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
        x: { title: { display: true, text: 'Date' } },
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

  _createQueryChartData(processedData) {
    const datasets = [
      {
        label: 'Execution Time (hours)',
        data: processedData.durations,
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 3,
        yAxisID: 'y',
      },
      {
        label: 'Cost',
        data: processedData.costs,
        borderColor: 'rgba(255, 159, 64, 1)',
        backgroundColor: 'rgba(255, 159, 64, 0.2)',
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
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
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
        shared_hit: 'rgba(153, 102, 255, 1)',
        shared_read: 'rgba(255, 99, 132, 1)',
        shared_dirtied: 'rgba(255, 206, 86, 1)',
        shared_written: 'rgba(0, 200, 83, 1)',
        temp_read: 'rgba(54, 162, 235, 1)',
        temp_written: 'rgba(255, 140, 0, 1)',
      };
      Object.entries(processedData.buffers).forEach(([key, data]) => {
        if (data.some((v) => v !== null)) {
          datasets.push({
            label: `Buffer ${key.replace('_', ' ')}`,
            data: data,
            borderColor: bufferColors[key],
            backgroundColor: bufferColors[key].replace('1)', '0.2)'),
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
        records: 'rgba(0, 123, 255, 1)',
        fpi: 'rgba(220, 53, 69, 1)',
        bytes: 'rgba(40, 167, 69, 1)',
      };
      Object.entries(processedData.wal).forEach(([key, data]) => {
        if (data.some((v) => v !== null)) {
          datasets.push({
            label: `WAL ${key}`,
            data: data,
            borderColor: walColors[key],
            backgroundColor: walColors[key].replace('1)', '0.2)'),
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
        borderColor: 'rgba(0, 128, 128, 1)',
        backgroundColor: 'rgba(0, 128, 128, 0.2)',
        fill: false,
        tension: 0.1,
        spanGaps: true,
        pointRadius: 2,
        yAxisID: 'yWAL',
        hidden: true,
      });
    }

    return { labels: processedData.labels, datasets };
  }

  _createQueryChartOptions(selectedDay, annotations) {
    return {
      responsive: true,
      plugins: {
        legend: {
          display: true,
          onClick: (e, legendItem, legend) => {
            const chart = legend.chart;
            Chart.defaults.plugins.legend.onClick.call(this, e, legendItem, legend);
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (ds) {
              const isVisible = typeof chart.isDatasetVisible === 'function' ? chart.isDatasetVisible(legendItem.datasetIndex) : !ds.hidden;
              if (ds.yAxisID === 'yCost') chart.options.scales.yCost.display = isVisible;
              else if (ds.yAxisID === 'yRows') chart.options.scales.yRows.display = isVisible;
              else if (ds.yAxisID === 'yBuffer') chart.options.scales.yBuffer.display = isVisible;
              else if (ds.yAxisID === 'yWAL') chart.options.scales.yWAL.display = isVisible;
              chart.update();
            }
          },
        },
        annotation: { annotations },
      },
      scales: {
        x: {
          type: 'category',
          title: { display: true, text: 'Timestamp' },
          ticks: {
            autoSkip: true,
            maxTicksLimit: 10,
            font: (ctx) => {
              const lbl = ctx.tick && ctx.tick.label;
              if (lbl === selectedDay) return { weight: 'bold' };
              return {};
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
