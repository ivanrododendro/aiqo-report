/**
 * Tab navigation utilities
 */
class TabNavigator {
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
}

/**
 * Daily tab content updater
 */
class DailyTabUpdater {
    constructor(reportData) {
        this.reportData = reportData;
    }

    /**
     * Update all content for a specific day tab
     */
    updateTabContent(day) {
        const currentDayStats = this.reportData.statistics.daily_stats[day];
        if (!currentDayStats) {
            console.warn(`No statistics found for day: ${day}`);
            return;
        }

        this._updateTotalQueries(day, currentDayStats);
        this._updateCumulatedTime(day, currentDayStats);
        this._updateQueriesByCodeTable(day, currentDayStats);
    }

    /**
     * Update total queries display
     */
    _updateTotalQueries(day, dayStats) {
        const element = document.getElementById(`total-queries-${ReportUtils.dateToSafeId(day)}`);
        if (element) {
            element.innerHTML = dayStats.total_queries || 0;
        }
    }

    /**
     * Update cumulated time display
     */
    _updateCumulatedTime(day, dayStats) {
        const element = document.getElementById(`cumulated-time-day-${ReportUtils.dateToSafeId(day)}`);
        if (element) {
            element.innerHTML = Duration.fromMillis(dayStats.cumulated_time || 0).toFormat("h'h'm'm's's'");
        }
    }

    /**
     * Update queries by code table
     */
    _updateQueriesByCodeTable(day, dayStats) {
        const tableBody = document.getElementById(`queries-by-code-table-body-${ReportUtils.dateToSafeId(day)}`);
        if (!tableBody || !dayStats.queries_by_code) return;

        const sortedQueries = Object.entries(dayStats.queries_by_code)
            .sort(([, durationA], [, durationB]) => durationB - durationA);

        const rows = sortedQueries.map(([code, durationMs]) => {
            const shortCode = code.substring(0, 6);
            const formattedDuration = Duration.fromMillis(durationMs).toFormat("h'h'm'm's's'");
            return `<tr><td>${shortCode}</td><td>${formattedDuration}</td></tr>`;
        });

        tableBody.innerHTML = rows.join('');
    }
}

/**
 * Event handler setup for navigation
 */
class NavigationEventHandler {
    constructor(reportData, tabNavigator, tabUpdater) {
        this.reportData = reportData;
        this.tabNavigator = tabNavigator;
        this.tabUpdater = tabUpdater;
    }

    /**
     * Setup all navigation event handlers
     */
    setupAllHandlers() {
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
                const day = this._extractDayFromTabEvent(event);
                this.tabUpdater.updateTabContent(day);
            });
        });

        // Trigger for initially active tab
        this._updateInitialActiveTab();
    }

    /**
     * Extract day from tab event
     */
    _extractDayFromTabEvent(event) {
        const targetTabPaneId = event.target.getAttribute('href').substring(1);
        // Tabs now use "YYYY-MM-DD" format directly
        return targetTabPaneId.replace('tab-', '');
    }

    /**
     * Update initially active tab
     */
    _updateInitialActiveTab() {
        const activeTabElement = document.querySelector('#dailyTabs .nav-link.active');
        if (activeTabElement) {
            const targetPaneId = activeTabElement.getAttribute('href').substring(1);
            const day = targetPaneId.replace('tab-', '');
            this.tabUpdater.updateTabContent(day);
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

                const targetDay = this.tabNavigator.findEarliestDayForQuery(code);
                if (targetDay) {
                    this.tabNavigator.navigateToQuery(code, targetDay);
                }
            });
        });
    }

    /**
     * Setup click handlers for charts
     */
    _setupChartClickHandlers() {
        const dailyChart = document.getElementById('dailyCumulatedTimeChart');
        if (dailyChart) {
            dailyChart.onclick = (evt) => this._handleDailyChartClick(evt);
        }
    }

    /**
     * Handle daily chart click
     */
    _handleDailyChartClick(evt) {
        const chart = window.reportChartManager.charts.dailyCumulatedTime;
        if (!chart) return;

        const points = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, false);
        if (!points.length) return;

        const idx = points[0].index;
        const day = chart.data.labels[idx];
        console.log(`📊 Click sul grafico per il giorno: ${day}`);
        this.tabNavigator.navigateToDay(day);
    }
}

/**
 * Main navigation manager for the report
 */
class ReportNavigator {
    constructor(reportData) {
        this.reportData = reportData;
        this.tabNavigator = new TabNavigator(reportData);
        this.tabUpdater = new DailyTabUpdater(reportData);
        this.eventHandler = new NavigationEventHandler(reportData, this.tabNavigator, this.tabUpdater);
    }

    /**
     * Navigate to a specific day tab
     */
    navigateToDay(day) {
        this.tabNavigator.navigateToDay(day);
    }

    /**
     * Navigate to a specific query within a day
     */
    navigateToQuery(queryCode, day) {
        this.tabNavigator.navigateToQuery(queryCode, day);
    }

    /**
     * Find the earliest day containing a specific query code
     */
    findEarliestDayForQuery(queryCode) {
        return this.tabNavigator.findEarliestDayForQuery(queryCode);
    }

    /**
     * Setup all navigation event handlers
     */
    setupNavigationHandlers() {
        this.eventHandler.setupAllHandlers();
    }
}
