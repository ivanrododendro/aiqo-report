/**
 * Navigation management for the report
 */
class ReportNavigator {
    constructor(reportData) {
        this.reportData = reportData;
    }

    /**
     * Navigate to a specific day tab
     */
    navigateToDay(day) {
        const tabId = `tab-${ReportUtils.dateToSafeId(day)}-tab`;
        const tabEl = document.getElementById(tabId);
        if (tabEl) {
            const tabInstance = bootstrap.Tab.getOrCreateInstance(tabEl);
            tabInstance.show();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    /**
     * Navigate to a specific query within a day
     */
    navigateToQuery(queryCode, day) {
        this.navigateToDay(day);

        setTimeout(() => {
            const selector = `#tab-${ReportUtils.dateToSafeId(day)} .accordion-button[data-query-code='${queryCode}']`;
            const btn = document.querySelector(selector);
            if (btn) {
                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (btn.classList.contains('collapsed')) {
                    btn.click();
                }
            }
        }, 200);
    }

    /**
     * Find the earliest day containing a specific query code
     */
    findEarliestDayForQuery(queryCode) {
        const allDays = this.reportData.charts.all_dates;
        const dailyStats = this.reportData.statistics.daily_stats;

        for (const day of allDays) {
            const dayStats = dailyStats[day];
            if (dayStats?.queries_by_code?.[queryCode] != null) {
                return day;
            }
        }
        return null;
    }

    /**
     * Setup all navigation event handlers
     */
    setupNavigationHandlers() {
        this._setupTabHandlers();
        this._setupGlobalQueryRowHandlers();
        this._setupChartClickHandlers();
    }

    /**
     * Setup tab change handlers
     */
    _setupTabHandlers() {
        const tabLinks = document.querySelectorAll('#dailyTabs .nav-link');
        
        tabLinks.forEach(tabLink => {
            tabLink.addEventListener('shown.bs.tab', (event) => {
                const targetTabPaneId = event.target.getAttribute('href').substring(1);
                const day = targetTabPaneId.replace('tab-', '').replace(/-/g, '.');
                this._updateDailyTabContent(day);
            });
        });

        // Trigger for initially active tab
        const activeTabElement = document.querySelector('#dailyTabs .nav-link.active');
        if (activeTabElement) {
            const targetPaneId = activeTabElement.getAttribute('href').substring(1);
            const day = targetPaneId.replace('tab-', '').replace(/-/g, '.');
            this._updateDailyTabContent(day);
        }
    }

    /**
     * Setup click handlers for global query rows
     */
    _setupGlobalQueryRowHandlers() {
        document.querySelectorAll('.global-query-row').forEach(row => {
            row.addEventListener('click', () => {
                const code = row.getAttribute('data-query-code');
                if (!code) return;

                const targetDay = this.findEarliestDayForQuery(code);
                if (targetDay) {
                    this.navigateToQuery(code, targetDay);
                }
            });
        });
    }

    /**
     * Setup click handlers for charts
     */
    _setupChartClickHandlers() {
        // Daily cumulated time chart
        const dailyChart = document.getElementById('dailyCumulatedTimeChart');
        if (dailyChart) {
            dailyChart.onclick = (evt) => {
                const chart = window.reportChartManager.charts.dailyCumulatedTime;
                if (!chart) return;

                const points = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
                if (!points.length) return;

                const idx = points[0].index;
                const day = chart.data.labels[idx];
                this.navigateToDay(day);
            };
        }
    }

    /**
     * Update daily tab content (summary and tables)
     */
    _updateDailyTabContent(day) {
        const currentDayStats = this.reportData.statistics.daily_stats[day];

        // Update total queries
        const totalQueriesSpan = document.getElementById(`total-queries-${ReportUtils.dateToSafeId(day)}`);
        if (totalQueriesSpan && currentDayStats) {
            totalQueriesSpan.innerHTML = currentDayStats.total_queries || 0;
        }

        // Update cumulated time
        const cumulatedTimeSpan = document.getElementById(`cumulated-time-day-${ReportUtils.dateToSafeId(day)}`);
        if (cumulatedTimeSpan && currentDayStats) {
            cumulatedTimeSpan.innerHTML = Duration.fromMillis(currentDayStats.cumulated_time || 0).toFormat("h'h'm'm's's'");
        }

        // Update queries by code table
        const queriesByCodeTableBody = document.getElementById(`queries-by-code-table-body-${ReportUtils.dateToSafeId(day)}`);
        if (queriesByCodeTableBody && currentDayStats && currentDayStats.queries_by_code) {
            const queriesByCode = currentDayStats.queries_by_code;
            let tableBodyHtml = '';
            const sortedQueries = Object.entries(queriesByCode).sort(([, durationA], [, durationB]) => durationB - durationA);

            for (const [code, durationMs] of sortedQueries) {
                tableBodyHtml += `<tr><td>${code.substring(0, 6)}</td><td>${Duration.fromMillis(durationMs).toFormat("h'h'm'm's's'")}</td></tr>`;
            }
            queriesByCodeTableBody.innerHTML = tableBodyHtml;
        }
    }
}
