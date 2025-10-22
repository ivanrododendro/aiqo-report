/**
 * Chart management for the report
 */
class ReportChartManager {
    constructor(reportData) {
        this.reportData = reportData;
        this.charts = {};
    }

    /**
     * Render the daily cumulated time and query count chart
     */
    renderDailyCumulatedTimeChart() {
        const ctx = document.getElementById('dailyCumulatedTimeChart');
        if (!ctx) return;

        const chartData = this.reportData.charts.daily_trends;
        const annotations = this._buildGenericAnnotations();

        this.charts.dailyCumulatedTime = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
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
                        yAxisID: 'y'
                    },
                    {
                        label: 'Total Queries Count',
                        data: chartData.total_queries,
                        type: 'bar',
                        backgroundColor: 'rgba(153, 102, 255, 0.5)',
                        borderColor: 'rgba(153, 102, 255, 1)',
                        borderWidth: 1,
                        yAxisID: 'yAxisRightTotalQueries'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Daily Cumulated Time and Query Count Trends'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
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
                            }
                        }
                    },
                    annotation: { annotations }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Date' }
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        title: { display: true, text: 'Cumulated Time (Minutes)' },
                        beginAtZero: true
                    },
                    yAxisRightTotalQueries: {
                        type: 'linear',
                        position: 'right',
                        title: { display: true, text: 'Total Queries Count' },
                        beginAtZero: true,
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });

        return this.charts.dailyCumulatedTime;
    }

    /**
     * Render execution time chart for a specific query
     */
    renderQueryExecutionChart(canvasId, queryCode, allExecutions, selectedDay) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;

        // Sort by timestamp
        allExecutions.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

        const labels = allExecutions.map(e => e.timestamp.split(' ')[0]);
        const data = allExecutions.map(e => e.duration !== null ? e.duration / 3600000 : null); // Convert ms to hours
        const dataCost = allExecutions.map(e => ReportUtils.parseCostValue(e.cost));
        const dataRows = allExecutions.map(e => ReportUtils.parseRowsValue(e.rows));

        const annotations = this._buildQueryAnnotations(canvasId, labels);

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Execution Time (hours)',
                        data: data,
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        fill: false,
                        tension: 0.1,
                        spanGaps: true,
                        pointRadius: 3,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Cost',
                        data: dataCost,
                        borderColor: 'rgba(255, 159, 64, 1)',
                        backgroundColor: 'rgba(255, 159, 64, 0.2)',
                        fill: false,
                        tension: 0.1,
                        spanGaps: true,
                        pointRadius: 3,
                        yAxisID: 'yCost'
                    },
                    {
                        label: 'Rows',
                        data: dataRows,
                        borderColor: 'rgba(54, 162, 235, 1)',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                        fill: false,
                        tension: 0.1,
                        spanGaps: true,
                        pointRadius: 3,
                        yAxisID: 'yRows',
                        hidden: true
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        display: true,
                        onClick: (e, legendItem, legend) => {
                            const chart = legend.chart;
                            Chart.defaults.plugins.legend.onClick.call(this, e, legendItem, legend);
                            const ds = chart.data.datasets[legendItem.datasetIndex];
                            if (ds && ds.yAxisID === 'yRows') {
                                const isVisible = typeof chart.isDatasetVisible === 'function'
                                    ? chart.isDatasetVisible(legendItem.datasetIndex)
                                    : !ds.hidden;
                                chart.options.scales.yRows.display = isVisible;
                                chart.update();
                            }
                        }
                    },
                    annotation: { annotations }
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
                                if (lbl === selectedDay) {
                                    return { weight: 'bold' };
                                }
                                return {};
                            }
                        }
                    },
                    y: {
                        title: { display: true, text: 'Execution Time (hours)' },
                        beginAtZero: true
                    },
                    yCost: {
                        type: 'linear',
                        position: 'right',
                        title: { display: true, text: 'Cost' },
                        beginAtZero: true,
                        grid: { drawOnChartArea: false }
                    },
                    yRows: {
                        type: 'linear',
                        position: 'right',
                        display: false,
                        offset: true,
                        title: { display: true, text: 'Rows' },
                        beginAtZero: true,
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });

        this.charts[canvasId] = chart;
        return chart;
    }

    /**
     * Build annotations for generic optimizations (server + event)
     */
    _buildGenericAnnotations() {
        const annotations = {};
        // Use safe path resolution to avoid breaking visualization when annotations are missing or structure differs
        const annotationsRoot = this.reportData.optimizations && this.reportData.optimizations.annotations;
        const genericAnnotations =
            (annotationsRoot && (annotationsRoot.generic || (annotationsRoot.annotations && annotationsRoot.annotations.generic))) || [];

        if (!Array.isArray(genericAnnotations) || genericAnnotations.length === 0) {
            console.debug("No generic annotations found, skipping annotation drawing.");
            return annotations;
        }

        genericAnnotations.forEach((ann, idx) => {
            const dateIndex = ReportUtils.findLabelIndex(
                this.reportData.charts.daily_trends.labels,
                ann.date
            );

            if (dateIndex !== -1) {
                annotations[`ann_${idx}`] = {
                    type: 'line',
                    mode: 'vertical',
                    xMin: ann.date,
                    xMax: ann.date,
                    borderColor: ann.border_color,
                    borderWidth: 2,
                    label: {
                        content: ann.id,
                        display: true,
                        position: 'top',
                        font: { size: 12, weight: 'bold' },
                        backgroundColor: ann.border_color.replace('0.8', '0.7'),
                        color: 'white',
                        rotation: 0,
                        yAdjust: -10
                    }
                };
            }
        });

        return annotations;
    }

    /**
     * Build annotations for query-specific optimizations
     */
    _buildQueryAnnotations(canvasId, labels) {
        const annotations = {};
        
        // Extract query code and app_id from canvas ID
        const parts = canvasId.split('-');
        // canvasId format: execTimeChart-app-YYYY-MM-DD-index
        
        // Find optimization lists in the DOM
        const queryOptList = document.querySelector(`#opt-list-${canvasId.replace('execTimeChart-', '')}`);
        const serverOptList = document.querySelector(`#server-opt-list-${canvasId.replace('execTimeChart-', '')}`);

        let counter = 0;

        // Process query optimizations
        if (queryOptList) {
            const items = Array.from(queryOptList.querySelectorAll('li[data-opt-date]'));
            items.forEach((li, idx) => {
                const number = (idx + 1).toString();
                const badge = li.querySelector('.opt-letter');
                if (badge) badge.textContent = `${number} `;
                
                const datePart = (li.dataset.optDate || '').split(' ')[0];
                const idxOnScale = ReportUtils.findLabelIndex(labels, datePart);
                
                if (idxOnScale !== -1) {
                    annotations[`ann_${counter}`] = {
                        type: 'line',
                        xScaleID: 'x',
                        yScaleID: 'y',
                        xMin: idxOnScale,
                        xMax: idxOnScale,
                        yMin: 'min',
                        yMax: 'max',
                        borderColor: 'rgba(255, 0, 0, 0.8)',
                        borderWidth: 2,
                        label: {
                            content: number,
                            enabled: true,
                            display: true,
                            position: 'start',
                            font: { size: 14, weight: 'bold' },
                            backgroundColor: 'rgba(255, 0, 0, 0.9)',
                            color: 'white',
                            rotation: 0,
                            yAdjust: 10,
                            xAdjust: 0,
                            padding: 4,
                            borderRadius: 3
                        }
                    };
                    counter++;
                }
            });
        }

        // Process server optimizations
        if (serverOptList) {
            const items = Array.from(serverOptList.querySelectorAll('li[data-opt-date]'));
            items.forEach((li, idx) => {
                const number = (idx + 1).toString();
                const labelText = `S${number}`;
                const badge = li.querySelector('.server-opt-label');
                if (badge) badge.textContent = `${labelText} `;
                
                const datePart = (li.dataset.optDate || '').split(' ')[0];
                const idxOnScale = ReportUtils.findLabelIndex(labels, datePart);
                
                if (idxOnScale !== -1) {
                    annotations[`ann_${counter}`] = {
                        type: 'line',
                        xScaleID: 'x',
                        yScaleID: 'y',
                        xMin: idxOnScale,
                        xMax: idxOnScale,
                        yMin: 'min',
                        yMax: 'max',
                        borderColor: 'rgba(0, 0, 255, 0.8)',
                        borderWidth: 2,
                        label: {
                            content: labelText,
                            enabled: true,
                            display: true,
                            position: 'start',
                            font: { size: 14, weight: 'bold' },
                            backgroundColor: 'rgba(0, 0, 255, 0.9)',
                            color: 'white',
                            rotation: 0,
                            yAdjust: 10,
                            xAdjust: 0,
                            padding: 4,
                            borderRadius: 3
                        }
                    };
                    counter++;
                }
            });
        }

        return annotations;
    }

    /**
     * Destroy a specific chart
     */
    destroyChart(chartId) {
        if (this.charts[chartId]) {
            this.charts[chartId].destroy();
            delete this.charts[chartId];
        }
    }
}
