/**
 * Annotation builder for Chart.js plugin-annotation
 */
;(function(){
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  AIQO.Core.AnnotationBuilder = class AnnotationBuilder {
  constructor(reportData) {
    this.reportData = reportData;
  }

  buildGenericAnnotations() {
    const annotations = {};
    const annotationsRoot = this.reportData.optimizations && this.reportData.optimizations.annotations;
    const genericAnnotations =
      (annotationsRoot && (annotationsRoot.generic || (annotationsRoot.annotations && annotationsRoot.annotations.generic))) || [];

    if (!Array.isArray(genericAnnotations) || genericAnnotations.length === 0) {
      console.debug('No generic annotations found, skipping annotation drawing.');
      return annotations;
    }

    genericAnnotations.forEach((ann, idx) => {
      const dateIndex = ReportUtils.findLabelIndex(this.reportData.charts.daily_trends.labels, ann.date);
      if (dateIndex !== -1) {
        annotations[`ann_${idx}`] = this._createGenericAnnotation(ann);
      }
    });

    return annotations;
  }

  buildQueryAnnotations(canvasId, labels) {
    const annotations = {};
    let counter = 0;

    const queryAnnotations = this._extractQueryOptimizations(canvasId, labels);
    const serverAnnotations = this._extractServerOptimizations(canvasId, labels);

    Object.keys(queryAnnotations).forEach((key) => {
      annotations[`ann_${counter}`] = queryAnnotations[key];
      counter++;
    });

    Object.keys(serverAnnotations).forEach((key) => {
      annotations[`ann_${counter}`] = serverAnnotations[key];
      counter++;
    });

    return annotations;
  }

  _createGenericAnnotation(ann) {
    return {
      type: 'line',
      mode: 'vertical',
      xMin: ann.date,
      xMax: ann.date,
      borderColor: ann.border_color,
      borderWidth: 2,
      label: {
        content: ann.id,
        display: true,
        position: 'top',
        font: { size: 12, weight: 'bold' },
        backgroundColor: ann.border_color.replace('0.8', '0.7'),
        color: 'white',
        rotation: 0,
        yAdjust: -10,
      },
    };
  }

  _extractQueryOptimizations(canvasId, labels) {
    const selector = `#opt-list-${canvasId.replace('execTimeChart-', '')}`;
    return this._processOptimizationList(selector, labels, 'query');
  }

  _extractServerOptimizations(canvasId, labels) {
    const selector = `#server-opt-list-${canvasId.replace('execTimeChart-', '')}`;
    return this._processOptimizationList(selector, labels, 'server');
  }

  _processOptimizationList(selector, labels, type) {
    const annotations = {};
    const list = document.querySelector(selector);
    if (!list) return annotations;

    const items = Array.from(list.querySelectorAll('li[data-opt-date]'));
    items.forEach((li, idx) => {
      const annotation = this._createAnnotationFromListItem(li, idx, labels, type);
      if (annotation) {
        annotations[`${type}_${idx}`] = annotation;
      }
    });

    return annotations;
  }

  _createAnnotationFromListItem(li, idx, labels, type) {
    const number = (idx + 1).toString();
    const labelText = type === 'server' ? `S${number}` : number;
    const badgeSelector = type === 'server' ? '.server-opt-label' : '.opt-letter';
    const color = type === 'server' ? 'rgba(0, 0, 255, 0.8)' : 'rgba(255, 0, 0, 0.8)';
    const bgColor = type === 'server' ? 'rgba(0, 0, 255, 0.9)' : 'rgba(255, 0, 0, 0.9)';

    const badge = li.querySelector(badgeSelector);
    if (badge) badge.textContent = `${labelText} `;

    const datePart = (li.dataset.optDate || '').split(' ')[0];
    const idxOnScale = ReportUtils.findLabelIndex(labels, datePart);
    if (idxOnScale === -1) return null;

    return {
      type: 'line',
      xScaleID: 'x',
      yScaleID: 'y',
      xMin: idxOnScale,
      xMax: idxOnScale,
      yMin: 'min',
      yMax: 'max',
      borderColor: color,
      borderWidth: 2,
      label: {
        content: labelText,
        enabled: true,
        display: true,
        position: 'start',
        font: { size: 14, weight: 'bold' },
        backgroundColor: bgColor,
        color: 'white',
        rotation: 0,
        yAdjust: 10,
        xAdjust: 0,
        padding: 4,
        borderRadius: 3,
      },
    };
  }
}
})();
