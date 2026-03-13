/**
 * Tab navigation utilities
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.TabNavigator = class TabNavigator {
    constructor(reportData) {
        this.reportData = reportData;
    }

    /**
     * Navigate to a specific year tab
     */
    navigateToYear(year) {
        const tabId = `tab-year-${year}-tab`;
        const tabEl = document.getElementById(tabId);
        if (tabEl) {
            const tabInstance = bootstrap.Tab.getOrCreateInstance(tabEl);
            tabInstance.show();
            // console.log(`✅ Navigato all'anno: ${year}`);
            return true;
        }
        console.error(`❌ Tab anno non trovato: ${year}`);
        return false;
    }

    /**
     * Navigate to a specific month tab
     */
    navigateToMonth(yearMonth) {
        // yearMonth format: "YYYY-MM"
        const year = yearMonth.substring(0, 4);
        
        // First navigate to the year
        if (!this.navigateToYear(year)) {
            return false;
        }

        // Wait for year tab to be shown, then navigate to month
        setTimeout(() => {
            const tabId = `tab-month-${yearMonth}-tab`;
            const tabEl = document.getElementById(tabId);
            if (tabEl) {
                const tabInstance = bootstrap.Tab.getOrCreateInstance(tabEl);
                tabInstance.show();
                // console.log(`✅ Navigato al mese: ${yearMonth}`);
            } else {
                console.error(`❌ Tab mese non trovato: ${yearMonth}`);
            }
        }, 100);
        
        return true;
    }

    /**
     * Navigate to a specific day tab
     */
    navigateToDay(day) {
        // day format: "YYYY-MM-DD"
        const year = day.substring(0, 4);
        const yearMonth = day.substring(0, 7);
        
        // First navigate to year
        if (!this.navigateToYear(year)) {
            return false;
        }

        // Then navigate to month
        setTimeout(() => {
            const monthTabId = `tab-month-${yearMonth}-tab`;
            const monthTabEl = document.getElementById(monthTabId);
            if (monthTabEl) {
                const monthTabInstance = bootstrap.Tab.getOrCreateInstance(monthTabEl);
                monthTabInstance.show();
                
                // Finally navigate to day
                setTimeout(() => {
                    const dayTabId = `tab-day-${ReportUtils.dateToSafeId(day)}-tab`;
                    const dayTabEl = document.getElementById(dayTabId);
                    if (dayTabEl) {
                        const dayTabInstance = bootstrap.Tab.getOrCreateInstance(dayTabEl);
                        dayTabInstance.show();
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                        // console.log(`✅ Navigato al giorno: ${day}`);
                    } else {
                        console.error(`❌ Tab giorno non trovato: ${day}`);
                    }
                }, 150);
            } else {
                console.error(`❌ Tab mese non trovato: ${yearMonth}`);
            }
        }, 100);
        
        return true;
    }

    /**
     * Navigate to a specific query within a day
     */
    navigateToQuery(queryCode, day) {
        // Navigate to the day first (which handles year and month navigation)
        this.navigateToDay(day);

        // Wait for all tabs to be shown, then navigate to the query tab
        setTimeout(() => {
            const queryTabId = `query-tab-${ReportUtils.dateToSafeId(day)}-`;
            const queryTabs = document.querySelectorAll(`[id^="${queryTabId}"]`);
            
            // Find the query tab with matching query code
            let targetQueryTab = null;
            queryTabs.forEach(tab => {
                if (tab.getAttribute('data-query-code') === queryCode) {
                    targetQueryTab = tab;
                }
            });
            
            if (targetQueryTab) {
                const tabInstance = bootstrap.Tab.getOrCreateInstance(targetQueryTab);
                tabInstance.show();
                targetQueryTab.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // console.log(`✅ Navigato alla query: ${queryCode} nel giorno ${day}`);
            } else {
                console.error(`❌ Tab query non trovato: ${queryCode} nel giorno ${day}`);
            }
        }, 400);
    }

    /**
     * Navigate to a specific query instance within a day by index
     */
    navigateToQueryInstance(day, index) {
        this.navigateToDay(day);

        setTimeout(() => {
            const safeDay = ReportUtils.dateToSafeId(day);
            const targetQueryTab = document.getElementById(`query-tab-${safeDay}-${index}`);

            if (targetQueryTab && typeof targetQueryTab.click === 'function') {
                targetQueryTab.click();
                targetQueryTab.scrollIntoView({ behavior: 'smooth', block: 'center' });
                return;
            }

            console.error(`Query tab instance not found: ${day} #${index}`);
        }, 400);
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
 * Date tab content updater (renamed from DailyTabUpdater for TAPPA 6)
 */
AIQO.Core.DateTabUpdater = class DateTabUpdater {
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
AIQO.Core.NavigationEventHandler = class NavigationEventHandler {
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
        // Daily chart click handled by GlobalSynthesis component
        ReportUtils.applyByteFormatting();
    }

    /**
     * Setup tab change handlers for year/month/day hierarchy
     */
    _setupTabHandlers() {
        // Setup year tab handlers
        const yearTabLinks = document.querySelectorAll('#yearTabs .nav-link');
        yearTabLinks.forEach(tabLink => {
            tabLink.addEventListener('shown.bs.tab', (event) => {
                // const year = event.target.textContent.trim();
                // console.log(`📅 Anno cambiato: ${year}`);
            });
        });

        // Setup month tab handlers
        const monthTabLinks = document.querySelectorAll('.month-tabs .nav-link');
        monthTabLinks.forEach(tabLink => {
            tabLink.addEventListener('shown.bs.tab', (event) => {
                // const monthName = event.target.textContent.trim();
                // console.log(`📅 Mese cambiato: ${monthName}`);
            });
        });

        // Setup day tab handlers
        const dayTabLinks = document.querySelectorAll('.day-tabs .nav-link');
        dayTabLinks.forEach(tabLink => {
            tabLink.addEventListener('shown.bs.tab', (event) => {
                const day = this._extractDayFromTabEvent(event);
                // console.log(`📅 Giorno cambiato: ${day}`);
                this.tabUpdater.updateTabContent(day);
            });
        });

        // Trigger for initially active day tab
        this._updateInitialActiveTab();
    }

    /**
     * Extract day from tab event
     */
    _extractDayFromTabEvent(event) {
        const targetTabPaneId = event.target.getAttribute('data-bs-target').substring(1);
        // Extract day from "tab-day-YYYY-MM-DD" format
        return targetTabPaneId.replace('tab-day-', '');
    }

    /**
     * Update initially active tab
     */
    _updateInitialActiveTab() {
        const activeDayTab = document.querySelector('.day-tabs .nav-link.active');
        if (activeDayTab) {
            const targetPaneId = activeDayTab.getAttribute('data-bs-target').substring(1);
            const day = targetPaneId.replace('tab-day-', '');
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
    // Daily chart click is now bound in the GlobalSynthesis component
}

/**
 * Main navigation manager for the report
 */
AIQO.Core.ReportNavigator = class ReportNavigator {
    constructor(reportData) {
        this.reportData = reportData;
        this.tabNavigator = new AIQO.Core.TabNavigator(reportData);
        this.tabUpdater = new AIQO.Core.DateTabUpdater(reportData);
        this.eventHandler = new AIQO.Core.NavigationEventHandler(reportData, this.tabNavigator, this.tabUpdater);
    }

    /**
     * Navigate to a specific year tab
     */
    navigateToYear(year) {
        this.tabNavigator.navigateToYear(year);
    }

    /**
     * Navigate to a specific month tab
     */
    navigateToMonth(yearMonth) {
        this.tabNavigator.navigateToMonth(yearMonth);
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
     * Navigate to a specific query instance within a day by index
     */
    navigateToQueryInstance(day, index) {
        this.tabNavigator.navigateToQueryInstance(day, index);
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

})();
