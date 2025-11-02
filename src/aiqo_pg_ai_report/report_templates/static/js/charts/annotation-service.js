/**
 * AnnotationService: builds annotations for charts from reportData (no DOM reads)
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.AnnotationService = class AnnotationService {
    constructor(reportData) {
      this.reportData = reportData || {};
    }

    // Build annotations for the daily chart from generic optimizations
    buildDailyAnnotations() {
      const annotations = {};
      const root = (this.reportData.optimizations && this.reportData.optimizations.annotations) || {};
      const list = Array.isArray(root.generic) ? root.generic
                 : (root.annotations && Array.isArray(root.annotations.generic) ? root.annotations.generic : []);
      if (!list || list.length === 0) return annotations;

      let i = 0;
      list.forEach((ann) => {
        const date = (ann && ann.date) ? ann.date : null;
        if (!date) return;
        annotations['ann_' + (i++)] = this._lineOnDate(date, ann && ann.id, ann && ann.border_color);
      });
      return annotations;
    }

    // Build annotations for a query chart from reportData.optimizations
    // - queryCode: string identifying the query
    // - labels: array of 'YYYY-MM-DD' strings for the x scale
    // - selectedDay: 'YYYY-MM-DD' string; server annotations are filtered to this day (UI parity)
    buildQueryAnnotations(queryCode, labels, selectedDay) {
      const annotations = {};
      if (!queryCode || !Array.isArray(labels) || labels.length === 0) return annotations;

      const opts = (this.reportData.optimizations || {});
      const queryMap = opts.query || {};
      const serverList = Array.isArray(opts.server) ? opts.server : [];

      // Query-specific annotations (numbered 1..N)
      const qList = Array.isArray(queryMap[queryCode]) ? queryMap[queryCode] : [];
      let qIdx = 1;
      qList.forEach((opt) => {
        const date = (opt && opt.date) ? String(opt.date).split(' ')[0] : null;
        if (!date) return;
        if (labels.indexOf(date) === -1) return;
        annotations['q_' + qIdx] = this._lineOnDate(date, String(qIdx), 'rgba(255, 0, 0, 0.8)', true);
        qIdx += 1;
      });

      // Server annotations for the selected day only (prefixed S1..)
      let sIdx = 1;
      if (selectedDay) {
        serverList
          .filter((opt) => opt && opt.date === selectedDay)
          .forEach((opt) => {
            const date = selectedDay;
            if (labels.indexOf(date) === -1) return;
            annotations['s_' + sIdx] = this._lineOnDate(date, 'S' + String(sIdx), 'rgba(0, 0, 255, 0.8)', true, true);
            sIdx += 1;
          });
      }

      return annotations;
    }

    // Create a vertical line annotation on a given date (YYYY-MM-DD)
    _lineOnDate(dateStr, labelText, borderColor, filledLabel = false, server = false) {
      const color = borderColor || (server ? 'rgba(0, 0, 255, 0.8)' : 'rgba(255, 0, 0, 0.8)');
      const bg = color.replace('0.8', '0.9');
      return {
        type: 'line',
        xMin: dateStr,
        xMax: dateStr,
        borderColor: color,
        borderWidth: 2,
        label: {
          display: true,
          content: labelText || '',
          position: 'start',
          font: { size: 12, weight: 'bold' },
          backgroundColor: filledLabel ? bg : undefined,
          color: filledLabel ? 'white' : undefined,
          rotation: 0,
          yAdjust: 10,
          padding: 4,
          borderRadius: 3,
        },
      };
    }
  }
})();

