/**
 * Data validation utilities for chart inputs
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.DataValidator = class DataValidator {
  static validateExecutionData(executions) {
    if (!Array.isArray(executions)) {
      throw new Error('Executions must be an array');
    }
    return executions.filter((e) => e.timestamp && e.duration !== undefined);
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
})();
