/**
 * Scale helper utilities for Chart.js axes
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.ScaleHelper = class ScaleHelper {
  static formatCompactNumber(value) {
    if (value === null || value === undefined || value === '') return '';

    const numericValue = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(numericValue)) return value;

    const absoluteValue = Math.abs(numericValue);
    if (absoluteValue < 1000) {
      if (Number.isInteger(numericValue)) return String(numericValue);
      return numericValue.toFixed(2).replace(/\.?0+$/, '');
    }

    const suffixes = [
      { value: 1e12, suffix: 'T' },
      { value: 1e9, suffix: 'B' },
      { value: 1e6, suffix: 'M' },
      { value: 1e3, suffix: 'K' },
    ];

    const compactEntry = suffixes.find((entry) => absoluteValue >= entry.value);
    if (!compactEntry) return String(numericValue);

    const compactValue = numericValue / compactEntry.value;
    if (Math.abs(compactValue) >= 1000) return numericValue.toExponential(1);

    return `${compactValue.toFixed(1).replace(/\.0$/, '')}${compactEntry.suffix}`;
  }

  static createCompactTickOptions() {
    return {
      callback: (value) => AIQO.Core.ScaleHelper.formatCompactNumber(value),
    };
  }

  static createTimeScale() {
    return {
      title: { display: true, text: 'Execution Time (hours)' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
    };
  }

  static createCostScale() {
    return {
      type: 'linear',
      position: 'right',
      display: false,
      title: { display: true, text: 'Cost' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
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
      ticks: this.createCompactTickOptions(),
      grid: { drawOnChartArea: false },
    };
  }

  static createBufferScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'Buffer Operations' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
      grid: { drawOnChartArea: false },
    };
  }

  static createWALScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'WAL Operations' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
      grid: { drawOnChartArea: false },
    };
  }

  static createCumulatedTimeScale() {
    return {
      type: 'linear',
      position: 'left',
      title: { display: true, text: 'Cumulated Time (Minutes)' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
    };
  }

  static createQueryCountScale() {
    return {
      type: 'linear',
      position: 'right',
      title: { display: true, text: 'Total Queries Count' },
      beginAtZero: true,
      ticks: this.createCompactTickOptions(),
      grid: { drawOnChartArea: false },
    };
  }
}
})();
