/**
 * Tab navigation utilities — delegates to AIQO.Sidebar for actual navigation.
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.TabNavigator = class TabNavigator {
    constructor(reportData) {
      this.reportData = reportData;
    }

    navigateToDay(day) {
      if (window.AIQO && AIQO.Sidebar && typeof AIQO.Sidebar.navigateToDay === 'function') {
        AIQO.Sidebar.navigateToDay(day);
        return true;
      }
      return false;
    }

    navigateToYear(year) {
      const yearData = (this.reportData.date_hierarchy.years || {})[year];
      if (!yearData) return false;
      const days = yearData.all_days || [];
      // Find most recent day with data
      for (let i = days.length - 1; i >= 0; i--) {
        if ((this.reportData.statistics.daily_stats || {})[days[i]]) {
          return this.navigateToDay(days[i]);
        }
      }
      if (days.length) return this.navigateToDay(days[days.length - 1]);
      return false;
    }

    navigateToMonth(yearMonth) {
      const year     = yearMonth.substring(0, 4);
      const monthNum = yearMonth.substring(5, 7);
      const monthData = ((this.reportData.date_hierarchy.years || {})[year] || {}).months || {};
      const month = monthData[monthNum];
      if (!month) return false;
      const days = month.days || [];
      for (let i = days.length - 1; i >= 0; i--) {
        if ((this.reportData.statistics.daily_stats || {})[days[i]]) {
          return this.navigateToDay(days[i]);
        }
      }
      if (days.length) return this.navigateToDay(days[days.length - 1]);
      return false;
    }

    navigateToQuery(queryCode, day) {
      this.navigateToDay(day);
      setTimeout(() => {
        const reports = (this.reportData.reports.by_day[day] || []);
        const idx = reports.findIndex((r) => r.code === queryCode);
        if (idx >= 0) {
          const safeDay = ReportUtils.dateToSafeId(day);
          const panel   = document.getElementById('day-panel-' + safeDay);
          if (panel) AIQO.Components.Tabs._activateQueryByIndex(panel, idx);
        }
      }, 350);
    }

    navigateToQueryInstance(day, index) {
      this.navigateToDay(day);
      setTimeout(() => {
        const safeDay = ReportUtils.dateToSafeId(day);
        const panel   = document.getElementById('day-panel-' + safeDay);
        if (panel) AIQO.Components.Tabs._activateQueryByIndex(panel, index);
      }, 350);
    }

    findEarliestDayForQuery(queryCode) {
      const allDays    = this.reportData.charts.all_dates || [];
      const dailyStats = this.reportData.statistics.daily_stats || {};
      for (const day of allDays) {
        if ((dailyStats[day] && dailyStats[day].queries_by_code || {})[queryCode] != null) {
          return day;
        }
      }
      return null;
    }

    findPreferredDayForQuery(queryCode) {
      const dailyStats = this.reportData.statistics.daily_stats || {};
      const currentDay = (
        window.AIQO
        && AIQO.Sidebar
        && typeof AIQO.Sidebar.getCurrentDay === 'function'
      ) ? AIQO.Sidebar.getCurrentDay() : null;

      if (
        currentDay
        && (dailyStats[currentDay] && dailyStats[currentDay].queries_by_code || {})[queryCode] != null
      ) {
        return currentDay;
      }

      return this.findEarliestDayForQuery(queryCode);
    }
  };

  // ── DateTabUpdater ────────────────────────────────────────────────────────

  AIQO.Core.DateTabUpdater = class DateTabUpdater {
    constructor(reportData) {
      this.reportData = reportData;
    }

    updateTabContent(day) {
      const stats = (this.reportData.statistics.daily_stats || {})[day];
      if (!stats) return;
      this._updateTotalQueries(day, stats);
      this._updateCumulatedTime(day, stats);
      this._updateQueriesByCodeTable(day, stats);
    }

    _updateTotalQueries(day, stats) {
      const el = document.getElementById('total-queries-' + ReportUtils.dateToSafeId(day));
      if (el) el.innerHTML = stats.total_queries || 0;
    }

    _updateCumulatedTime(day, stats) {
      const el = document.getElementById('cumulated-time-day-' + ReportUtils.dateToSafeId(day));
      if (el) el.innerHTML = Duration.fromMillis(stats.cumulated_time || 0).toFormat("h'h' m'm' s's'");
    }

    _updateQueriesByCodeTable(day, stats) {
      const tbody = document.getElementById('queries-by-code-table-body-' + ReportUtils.dateToSafeId(day));
      if (!tbody || !stats.queries_by_code) return;
      const sorted = Object.entries(stats.queries_by_code)
        .sort(([, a], [, b]) => b - a);
      tbody.innerHTML = sorted
        .map(([code, ms]) =>
          '<tr><td>' + code.substring(0, 6) + '</td><td>' +
          Duration.fromMillis(ms).toFormat("h'h' m'm' s's'") + '</td></tr>'
        )
        .join('');
    }
  };

  // ── NavigationEventHandler ────────────────────────────────────────────────

  AIQO.Core.NavigationEventHandler = class NavigationEventHandler {
    constructor(reportData, tabNavigator, tabUpdater) {
      this.reportData    = reportData;
      this.tabNavigator  = tabNavigator;
      this.tabUpdater    = tabUpdater;
    }

    setupAllHandlers() {
      this._setupGlobalQueryRowHandlers();
      ReportUtils.applyByteFormatting();
    }

    _setupGlobalQueryRowHandlers() {
      document.querySelectorAll('.global-query-row').forEach((row) => {
        row.addEventListener('click', () => {
          const code = row.getAttribute('data-query-code');
          if (!code) return;
          const targetDay = this.tabNavigator.findPreferredDayForQuery(code);
          if (targetDay) this.tabNavigator.navigateToQuery(code, targetDay);
        });
      });
    }
  };

  // ── ReportNavigator ───────────────────────────────────────────────────────

  AIQO.Core.ReportNavigator = class ReportNavigator {
    constructor(reportData) {
      this.reportData   = reportData;
      this.tabNavigator = new AIQO.Core.TabNavigator(reportData);
      this.tabUpdater   = new AIQO.Core.DateTabUpdater(reportData);
      this.eventHandler = new AIQO.Core.NavigationEventHandler(
        reportData, this.tabNavigator, this.tabUpdater
      );
    }

    navigateToYear(year)                { return this.tabNavigator.navigateToYear(year); }
    navigateToMonth(yearMonth)          { return this.tabNavigator.navigateToMonth(yearMonth); }
    navigateToDay(day)                  { return this.tabNavigator.navigateToDay(day); }
    navigateToQuery(queryCode, day)     { return this.tabNavigator.navigateToQuery(queryCode, day); }
    navigateToQueryInstance(day, index) { return this.tabNavigator.navigateToQueryInstance(day, index); }
    findEarliestDayForQuery(code)       { return this.tabNavigator.findEarliestDayForQuery(code); }
    findPreferredDayForQuery(code)      { return this.tabNavigator.findPreferredDayForQuery(code); }

    setupNavigationHandlers() {
      this.eventHandler.setupAllHandlers();
    }
  };

})();
