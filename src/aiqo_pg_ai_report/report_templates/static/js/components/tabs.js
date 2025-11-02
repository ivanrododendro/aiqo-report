/**
 * Tabs component logic (year/month/day containers and query tab UX)
 */
;(function () {
  window.AIQO = window.AIQO || {};
  AIQO.Components = AIQO.Components || {};

  AIQO.Components.Tabs = {
    init() {
      // Initialize Split.js two-pane layout for all day containers
      document.querySelectorAll('[id^="split-container-"]').forEach((container) => {
        const leftPane = container.querySelector('.split:nth-child(1)');
        const rightPane = container.querySelector('.split:nth-child(2)');
        if (!leftPane || !rightPane || typeof Split !== 'function') return;
        try {
          Split([leftPane, rightPane], {
            sizes: [30, 70],
            minSize: [150, 300],
            gutterSize: 6,
            cursor: 'col-resize',
            gutter: function (index, direction) {
              const gutter = document.createElement('div');
              gutter.className = 'gutter gutter-' + direction;
              gutter.style.background = '#ddd';
              gutter.style.cursor = 'col-resize';
              gutter.style.width = '6px';
              return gutter;
            },
          });
        } catch (e) {
          console.warn('Split init failed for container', container.id, e);
        }
      });

      // Year tab change: show corresponding month container and activate last month
      document.querySelectorAll('[id^="tab-year-"]').forEach((yearTab) => {
        yearTab.addEventListener('shown.bs.tab', function (e) {
          const m = e.target.id.match(/tab-year-(\d+)-tab/);
          if (!m) return;
          const year = m[1];

          // Hide all month containers, then show the selected year
          document
            .querySelectorAll('.month-tabs-container')
            .forEach((el) => el.classList.add('d-none'));
          const monthContainer = document.getElementById(
            `month-tabs-container-${year}`
          );
          if (monthContainer) {
            monthContainer.classList.remove('d-none');
            // Activate last (most recent) month tab
            const monthTabs = monthContainer.querySelectorAll('.nav-link');
            if (monthTabs.length > 0) {
              const lastMonthTab = monthTabs[monthTabs.length - 1];
              bootstrap.Tab.getOrCreateInstance(lastMonthTab).show();
            }
          }
        });
      });

      // Month tab change: show corresponding day container/content and activate last day
      document.querySelectorAll('[id^="tab-month-"]').forEach((monthTab) => {
        monthTab.addEventListener('shown.bs.tab', function (e) {
          const m = e.target.id.match(/tab-month-(.+)-tab/);
          if (!m) return;
          const yearMonth = m[1];

          // Hide all day containers, then show the selected month
          document
            .querySelectorAll('.day-tabs-container')
            .forEach((el) => el.classList.add('d-none'));
          const dayContainer = document.getElementById(
            `day-tabs-container-${yearMonth}`
          );
          if (dayContainer) {
            dayContainer.classList.remove('d-none');
            // Activate last (most recent) day tab
            const dayTabs = dayContainer.querySelectorAll('.nav-link');
            if (dayTabs.length > 0) {
              const lastDayTab = dayTabs[dayTabs.length - 1];
              bootstrap.Tab.getOrCreateInstance(lastDayTab).show();
            }
          }

          // Hide all day tab contents, then show selected month content
          document
            .querySelectorAll('.day-tab-content')
            .forEach((el) => el.classList.add('d-none'));
          const dayTabContent = document.getElementById(
            `dayTabContent-${yearMonth}`
          );
          if (dayTabContent) {
            dayTabContent.classList.remove('d-none');
          }
        });
      });

      // Double-click on a query tab button -> copy short code to clipboard
      document.querySelectorAll('.query-tabs .nav-link').forEach((btn) => {
        btn.addEventListener('dblclick', function () {
          const fullCode = this.dataset.queryCode;
          if (!fullCode) return;
          const shortCode = fullCode.substring(0, 8);
          navigator.clipboard
            .writeText(shortCode)
            .then(() => {
              const toast = document.createElement('div');
              toast.className =
                'alert alert-success position-fixed top-0 end-0 m-3 py-2 px-3 shadow';
              toast.textContent = `Codice corto "${shortCode}" copiato negli appunti!`;
              document.body.appendChild(toast);
              setTimeout(() => toast.remove(), 2000);
            })
            .catch((err) => console.error('Clipboard error:', err));
        });
      });
    },
  };
})();
