/**
 * Chart configurations
 */
const CHART_CONFIGS = {
    dailyCumulatedTime: {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Daily Cumulated Time and Query Count Trends'
                }
            }
        }
    },
    queryExecution: {
        type: 'line',
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: true
                }
            }
        }
    }
};

/**
 * Scale helper utilities
 */
class ScaleHelper {
    static createTimeScale() {
        return {
            title: { display: true, text: 'Execution Time (hours)' },
            beginAtZero: true
        };
    }
    
    static createCostScale() {
        return {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Cost' },
            beginAtZero: true,
            grid: { drawOnChartArea: false }
        };
    }

    static createRowsScale() {
        return {
            type: 'linear',
            position: 'right',
            display: false,
            offset: true,
            title: { display: true, text: 'Rows' },
            beginAtZero: true,
            grid: { drawOnChartArea: false }
        };
    }

    static createBufferScale() {
        return {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Buffer Operations' },
            beginAtZero: true,
            grid: { drawOnChartArea: false }
        };
    }

    static createWALScale() {
        return {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'WAL Operations' },
            beginAtZero: true,
            grid: { drawOnChartArea: false }
        };
    }

    static createCumulatedTimeScale() {
        return {
            type: 'linear',
            position: 'left',
            title: { display: true, text: 'Cumulated Time (Minutes)' },
            beginAtZero: true
        };
    }

    static createQueryCountScale() {
        return {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'Total Queries Count' },
            beginAtZero: true,
            grid: { drawOnChartArea: false }
        };
    }
}

/**
 * Data validation utilities
 */
class DataValidator {
    static validateExecutionData(executions) {
        if (!Array.isArray(executions)) {
            throw new Error('Executions must be an array');
        }
        return executions.filter(e => e.timestamp && e.duration !== undefined);
    }

    static validateChartData(chartData) {
        const required = ['labels', 'cumulated_time', 'total_queries'];
        for (const field of required) {
            if (!chartData[field]) {
                throw new Error(`Missing required field: ${field}`);
            }
        }
        return chartData;
    }
}

/**
 * Annotation builder for charts
 */
class AnnotationBuilder {
    constructor(reportData) {
        this.reportData = reportData;
    }

    buildGenericAnnotations() {
        const annotations = {};
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
                annotations[`ann_${idx}`] = this._createGenericAnnotation(ann);
            }
        });

        return annotations;
    }

    buildQueryAnnotations(canvasId, labels) {
        const annotations = {};
        let counter = 0;

        const queryAnnotations = this._extractQueryOptimizations(canvasId, labels);
        const serverAnnotations = this._extractServerOptimizations(canvasId, labels);

        Object.keys(queryAnnotations).forEach(key => {
            annotations[`ann_${counter}`] = queryAnnotations[key];
            counter++;
        });

        Object.keys(serverAnnotations).forEach(key => {
            annotations[`ann_${counter}`] = serverAnnotations[key];
            counter++;
        });

        return annotations;
    }

    _createGenericAnnotation(ann) {
        return {
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

    _extractQueryOptimizations(canvasId, labels) {
        const selector = `#opt-list-${canvasId.replace('execTimeChart-', '')}`;
        return this._processOptimizationList(selector, labels, 'query');
    }

    _extractServerOptimizations(canvasId, labels) {
        const selector = `#server-opt-list-${canvasId.replace('execTimeChart-', '')}`;
        return this._processOptimizationList(selector, labels, 'server');
    }

    _processOptimizationList(selector, labels, type) {
        const annotations = {};
        const list = document.querySelector(selector);
        
        if (!list) return annotations;

        const items = Array.from(list.querySelectorAll('li[data-opt-date]'));
        items.forEach((li, idx) => {
            const annotation = this._createAnnotationFromListItem(li, idx, labels, type);
            if (annotation) {
                annotations[`${type}_${idx}`] = annotation;
            }
        });

        return annotations;
    }

    _createAnnotationFromListItem(li, idx, labels, type) {
        const number = (idx + 1).toString();
        const labelText = type === 'server' ? `S${number}` : number;
        const badgeSelector = type === 'server' ? '.server-opt-label' : '.opt-letter';
        const color = type === 'server' ? 'rgba(0, 0, 255, 0.8)' : 'rgba(255, 0, 0, 0.8)';
        const bgColor = type === 'server' ? 'rgba(0, 0, 255, 0.9)' : 'rgba(255, 0, 0, 0.9)';

        const badge = li.querySelector(badgeSelector);
        if (badge) badge.textContent = `${labelText} `;
        
        const datePart = (li.dataset.optDate || '').split(' ')[0];
        const idxOnScale = ReportUtils.findLabelIndex(labels, datePart);
        
        if (idxOnScale === -1) return null;

        return {
            type: 'line',
            xScaleID: 'x',
            yScaleID: 'y',
            xMin: idxOnScale,
            xMax: idxOnScale,
            yMin: 'min',
            yMax: 'max',
            borderColor: color,
            borderWidth: 2,
            label: {
                content: labelText,
                enabled: true,
                display: true,
                position: 'start',
                font: { size: 14, weight: 'bold' },
                backgroundColor: bgColor,
                color: 'white',
                rotation: 0,
                yAdjust: 10,
                xAdjust: 0,
                padding: 4,
                borderRadius: 3
            }
        };
    }
}

/**
 * Chart factory for creating different types of charts
 */
class ChartFactory {
    constructor(reportData) {
        this.reportData = reportData;
        this.annotationBuilder = new AnnotationBuilder(reportData);
    }

    createDailyCumulatedTimeChart(ctx) {
        try {
            const chartData = DataValidator.validateChartData(this.reportData.charts.daily_trends);
            const annotations = this.annotationBuilder.buildGenericAnnotations();

            return new Chart(ctx, {
                type: 'line',
                data: this._createDailyChartData(chartData),
                options: this._createDailyChartOptions(annotations)
            });
        } catch (error) {
            console.error('Failed to create daily chart:', error);
            return null;
        }
    }

    createQueryExecutionChart(ctx, canvasId, queryCode, allExecutions, selectedDay) {
        try {
            const validExecutions = DataValidator.validateExecutionData(allExecutions);
            const processedData = this._processExecutionData(validExecutions);
            const annotations = this.annotationBuilder.buildQueryAnnotations(canvasId, processedData.labels);

            return new Chart(ctx, {
                type: 'line',
                data: this._createQueryChartData(processedData),
                options: this._createQueryChartOptions(selectedDay, annotations)
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
        };
    }

    _createDailyChartOptions(annotations) {
        return {
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
                y: ScaleHelper.createCumulatedTimeScale(),
                yAxisRightTotalQueries: ScaleHelper.createQueryCountScale()
            }
        };
    }

    _processExecutionData(executions) {
        executions.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

        return {
            labels: executions.map(e => e.timestamp.split(' ')[0]),
            durations: executions.map(e => e.duration !== null ? e.duration / 3600000 : null),
            costs: executions.map(e => ReportUtils.parseCostValue(e.cost)),
            rows: executions.map(e => ReportUtils.parseRowsValue(e.rows)),
            buffers: {
                shared_hit: executions.map(e => e.buffers?.shared_hit ?? null),
                shared_read: executions.map(e => e.buffers?.shared_read ?? null),
                shared_dirtied: executions.map(e => e.buffers?.shared_dirtied ?? null),
                shared_written: executions.map(e => e.buffers?.shared_written ?? null),
                temp_read: executions.map(e => e.buffers?.temp_read ?? null),
                temp_written: executions.map(e => e.buffers?.temp_written ?? null)
            },
            wal: {
                records: executions.map(e => e.wal?.records ?? null),
                fpi: executions.map(e => e.wal?.fpi ?? null),
                bytes: executions.map(e => e.wal?.bytes ?? null)
            },
            io_total: executions.map(e => {
                const shared_read = e.buffers?.shared_read ?? 0;
                const shared_dirtied = e.buffers?.shared_dirtied ?? 0;
                const wal_bytes = e.wal?.bytes ?? 0;
                const total = shared_read + shared_dirtied + wal_bytes;
                return (shared_read || shared_dirtied || wal_bytes) ? total : null;
            })
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
                yAxisID: 'y'
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
                yAxisID: 'yCost'
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
                hidden: true
            }
        ];

        // Add buffer datasets if data exists
        if (processedData.buffers) {
            const bufferColors = {
                shared_hit: 'rgba(153, 102, 255, 1)',
                shared_read: 'rgba(255, 99, 132, 1)',
                shared_dirtied: 'rgba(255, 206, 86, 1)',
                shared_written: 'rgba(75, 192, 192, 1)',
                temp_read: 'rgba(54, 162, 235, 1)',
                temp_written: 'rgba(201, 203, 207, 1)'
            };

            Object.entries(processedData.buffers).forEach(([key, data]) => {
                if (data.some(v => v !== null)) {
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
                        hidden: true
                    });
                }
            });
        }

        // Add WAL datasets if data exists
        if (processedData.wal) {
            const walColors = {
                records: 'rgba(255, 159, 64, 1)',
                fpi: 'rgba(153, 102, 255, 1)',
                bytes: 'rgba(255, 99, 132, 1)'
            };

            Object.entries(processedData.wal).forEach(([key, data]) => {
                if (data.some(v => v !== null)) {
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
                        hidden: true
                    });
                }
            });
        }

        if (processedData.io_total && processedData.io_total.some(v => v !== null)) {
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
                hidden: false
            });
        }

        return {
            labels: processedData.labels,
            datasets: datasets
        };
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
                        
                        // Toggle visibility of corresponding axis
                        if (ds) {
                            const isVisible = typeof chart.isDatasetVisible === 'function'
                                ? chart.isDatasetVisible(legendItem.datasetIndex)
                                : !ds.hidden;
                            
                            if (ds.yAxisID === 'yRows') {
                                chart.options.scales.yRows.display = isVisible;
                            } else if (ds.yAxisID === 'yBuffer') {
                                chart.options.scales.yBuffer.display = isVisible;
                            } else if (ds.yAxisID === 'yWAL') {
                                chart.options.scales.yWAL.display = isVisible;
                            }
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
                y: ScaleHelper.createTimeScale(),
                yCost: ScaleHelper.createCostScale(),
                yRows: ScaleHelper.createRowsScale(),
                yBuffer: Object.assign(ScaleHelper.createBufferScale(), { display: false }),
                yWAL: Object.assign(ScaleHelper.createWALScale(), { display: false })
            }
        };
    }
}

/**
 * Chart management for the report
 */
class ReportChartManager {
    constructor(reportData) {
        this.reportData = reportData;
        this.chartFactory = new ChartFactory(reportData);
        this.charts = {};
    }

    /**
     * Render the daily cumulated time and query count chart
     */
    renderDailyCumulatedTimeChart() {
        const ctx = document.getElementById('dailyCumulatedTimeChart');
        if (!ctx) {
            console.warn('Daily chart canvas not found');
            return null;
        }

        this.charts.dailyCumulatedTime = this.chartFactory.createDailyCumulatedTimeChart(ctx.getContext('2d'));
        return this.charts.dailyCumulatedTime;
    }

    /**
     * Render execution time chart for a specific query
     */
    renderQueryExecutionChart(canvasId, queryCode, allExecutions, selectedDay) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.warn(`Query chart canvas not found: ${canvasId}`);
            return null;
        }

        this.charts[canvasId] = this.chartFactory.createQueryExecutionChart(
            ctx.getContext('2d'), canvasId, queryCode, allExecutions, selectedDay
        );
        return this.charts[canvasId];
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
