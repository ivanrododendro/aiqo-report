/**
 * Scale helper utilities for Chart.js axes
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.ScaleHelper = class ScaleHelper {
  static createTimeScale() {
    return {
      title: { display: true, text: 'Execution Time (hours)' },
      beginAtZero: true,
    };
  }

  static createCostScale() {
    return {
      type: 'linear',
      position: 'right',
      display: false,
      title: { display: true, text: 'Cost' },
      beginAtZero: true,
      grid: { drawOnChartArea: false },
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
      grid: { drawOnChartArea: false },
    };
  }

  static createBufferScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'Buffer Operations' },
      beginAtZero: true,
      grid: { drawOnChartArea: false },
    };
  }

  static createWALScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'WAL Operations' },
      beginAtZero: true,
      grid: { drawOnChartArea: false },
    };
  }

  static createCumulatedTimeScale() {
    return {
      type: 'linear',
      position: 'left',
      title: { display: true, text: 'Cumulated Time (Minutes)' },
      beginAtZero: true,
    };
  }

  static createQueryCountScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'Total Queries Count' },
      beginAtZero: true,
      grid: { drawOnChartArea: false },
    };
  }
}
})();
