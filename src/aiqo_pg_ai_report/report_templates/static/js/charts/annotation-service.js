/**
 * AnnotationService: builds annotations for charts from reportData (no DOM reads)
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.AnnotationService = class AnnotationService {
    static COLORS = {
      query: 'rgba(25, 135, 84, 0.8)',   // green
      server: 'rgba(13, 110, 253, 0.8)', // blue
      generic: 'rgba(108, 117, 125, 0.8)' // grey for events
    };

    constructor(reportData) {
      this.reportData = reportData || {};
    }

    // Build annotations for the daily chart from generic optimizations
    buildDailyAnnotations(options = {}) {
      const annotations = {};
      const root = (this.reportData.optimizations && this.reportData.optimizations.annotations) || {};
      const list = Array.isArray(root.generic) ? root.generic
                 : (root.annotations && Array.isArray(root.annotations.generic) ? root.annotations.generic : []);
      if (!list || list.length === 0) return annotations;

      const includeServer = options.includeServer !== false;
      const includeEvents = options.includeEvents !== false;

      let i = 0;
      list.forEach((ann) => {
        const date = (ann && ann.date) ? ann.date : null;
        if (!date) return;
        const type = ann && ann.type ? ann.type : null;
        if (type === 'Serveur' && !includeServer) return;
        if (type === 'Événement' && !includeEvents) return;
        const isServer = type === 'Serveur';
        const filled = isServer;
        annotations['ann_' + (i++)] = this._lineOnDate(
          date,
          ann && ann.id,
          ann && ann.border_color,
          filled,
          isServer,
          0
        );
      });
      return annotations;
    }

    // Build annotations for a query chart from reportData.optimizations
    // - queryCode: string identifying the query
    // - labels: array of 'YYYY-MM-DD' strings for the x scale
    // - selectedDay: 'YYYY-MM-DD' string; server annotations are filtered to this day (UI parity)
    // - options: { includeQuery?: boolean, includeServer?: boolean, includeGeneric?: boolean }
    buildQueryAnnotations(queryCode, labels, selectedDay, options = {}) {
      const annotations = {};
      if (!queryCode || !Array.isArray(labels) || labels.length === 0) return annotations;

      const reportOpts = (this.reportData.optimizations || {});
      const queryMap = reportOpts.query || {};
      const annotationsRoot = reportOpts.annotations || {};
      const genericAnnotations = Array.isArray(annotationsRoot.generic)
        ? annotationsRoot.generic
        : (annotationsRoot.annotations && Array.isArray(annotationsRoot.annotations.generic))
        ? annotationsRoot.annotations.generic
        : [];
      const legendEntries = (annotationsRoot.legend_entries && Array.isArray(annotationsRoot.legend_entries.generic))
        ? annotationsRoot.legend_entries.generic
        : [];

      const legendById = {};
      legendEntries.forEach((entry) => {
        if (entry && entry.id) {
          legendById[entry.id] = entry;
        }
      });

      const serverAnnotations = [];
      const eventAnnotations = [];
      genericAnnotations.forEach((ann) => {
        if (!ann || !ann.id) return;
        const meta = legendById[ann.id];
        if (!meta) return;
        if (meta.type === 'Serveur') {
          serverAnnotations.push({ ann, meta });
        } else if (meta.type === 'Événement') {
          eventAnnotations.push({ ann, meta });
        }
      });

      const includeQuery = (options && typeof options.includeQuery === 'boolean') ? options.includeQuery : true;
      const includeServer = (options && typeof options.includeServer === 'boolean') ? options.includeServer : true;
      const includeGeneric = (options && typeof options.includeGeneric === 'boolean') ? options.includeGeneric : false;

      // Query-specific annotations (numbered 1..N)
      if (includeQuery) {
        const qList = Array.isArray(queryMap[queryCode]) ? queryMap[queryCode] : [];
        let qIdx = 1;
        qList.forEach((opt) => {
          const date = (opt && opt.date) ? String(opt.date).split(' ')[0] : null;
          if (!date) return;
          if (labels.indexOf(date) === -1) return;
          // Raise labels ~10px compared to legacy (use yAdjust=0 vs default 10)
          annotations['q_' + qIdx] = this._lineOnDate(date, String(qIdx), AIQO.Core.AnnotationService.COLORS.query, true, false, 0);
          qIdx += 1;
        });
      }

      // Server annotations across the full date range
      if (includeServer) {
        let sIdx = 1;
        serverAnnotations.forEach(({ ann, meta }) => {
          const date = ann && ann.date ? String(ann.date).split(' ')[0] : null;
          if (!date) return;
          if (labels.indexOf(date) === -1) return;
          const labelText = meta && meta.id ? String(meta.id) : 'S' + String(sIdx);
          annotations['s_' + labelText] = this._lineOnDate(
            date,
            labelText,
            (ann && ann.border_color) || AIQO.Core.AnnotationService.COLORS.server,
            true,
            true,
            0
          );
          sIdx += 1;
        });
      }

      // Optional: Generic annotations layer (global context)
      if (includeGeneric && eventAnnotations.length > 0) {
        let gIdx = 1;
        eventAnnotations.forEach(({ ann, meta }) => {
          const date = ann && ann.date ? String(ann.date).split(' ')[0] : null;
          if (!date) return;
          if (labels.indexOf(date) === -1) return;
          const labelText = meta && meta.id ? String(meta.id) : 'G' + String(gIdx);
          annotations['g_' + labelText] = this._lineOnDate(
            date,
            labelText,
            (ann && ann.border_color) || AIQO.Core.AnnotationService.COLORS.generic,
            false,
            false,
            0
          );
          gIdx += 1;
        });
      }

      return annotations;
    }

    // Create a vertical line annotation on a given date (YYYY-MM-DD)
    // yAdjust: pixels offset for the label (positive moves down). Default 10 for legacy behavior.
    _lineOnDate(dateStr, labelText, borderColor, filledLabel = false, server = false, yAdjust = 10) {
      const color = borderColor || (server ? AIQO.Core.AnnotationService.COLORS.server : AIQO.Core.AnnotationService.COLORS.query);
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
          yAdjust: yAdjust,
          padding: 4,
          borderRadius: 3,
        },
      };
    }
  }
})();
