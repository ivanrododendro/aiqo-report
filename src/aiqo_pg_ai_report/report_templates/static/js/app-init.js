/**
 * App bootstrap: wires core managers and components in order
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Init = AIQO.Init || {};

  function initializeBootstrapTooltips() {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((element) => {
      bootstrap.Tooltip.getOrCreateInstance(element, {
        container: 'body',
        trigger: 'hover focus',
      });
    });
  }

  AIQO.Init.run = function(){
    // Core managers
    window.reportChartManager = new AIQO.Core.ReportChartManager(reportData);
    window.reportNavigator = new AIQO.Core.ReportNavigator(reportData);

    // Components
    if (AIQO.Components && AIQO.Components.Tabs) AIQO.Components.Tabs.init();
    if (AIQO.Components && AIQO.Components.GlobalSynthesis) AIQO.Components.GlobalSynthesis.init();

    // Navigation handlers (after components, so DOM hooks exist)
    if (window.reportNavigator && typeof window.reportNavigator.setupNavigationHandlers === 'function'){
      window.reportNavigator.setupNavigationHandlers();
    }

    if (AIQO.Components && AIQO.Components.QueryDetails) AIQO.Components.QueryDetails.init();
    initializeBootstrapTooltips();
  };
})();
