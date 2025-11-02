;(() => {
/**
 * Utility functions for the report (namespaced + global alias)
 */
  window.AIQO = window.AIQO || {};
  AIQO.Core = AIQO.Core || {};

  const ReportUtils = {
    /**
     * Generate a random RGB color
     */
    getRandomColor() {
        const r = Math.floor(Math.random() * 255);
        const g = Math.floor(Math.random() * 255);
        const b = Math.floor(Math.random() * 255);
        return 'rgb(' + r + ', ' + g + ', ' + b + ')';
    },

    /**
     * Parse cost value from various formats
     */
    parseCostValue(val) {
        if (val === null || val === undefined) return null;
        if (typeof val === 'number' && isFinite(val)) return val;
        if (typeof val === 'string') {
            const trimmed = val.trim();
            const rangeMatch = trimmed.match(/^(\d+(?:\.\d+)?)\.\.(\d+(?:\.\d+)?)/);
            if (rangeMatch) return parseFloat(rangeMatch[2]);
            const n = parseFloat(trimmed.replace(/[^0-9.-]/g, ''));
            return Number.isFinite(n) ? n : null;
        }
        return null;
    },

    /**
     * Parse rows value from various formats
     */
    parseRowsValue(val) {
        if (val === null || val === undefined) return null;
        if (typeof val === 'number' && isFinite(val)) return val;
        if (typeof val === 'string') {
            const n = parseInt(val.replace(/[^0-9-]/g, ''), 10);
            return Number.isFinite(n) ? n : null;
        }
        return null;
    },

    /**
     * Find label index in array; expects already-normalized "YYYY-MM-DD"
     */
    findLabelIndex(labels, dateStr) {
        if (!dateStr) return -1;
        return labels.indexOf(dateStr);
    },

    /**
     * Convert date string to safe HTML ID (no normalization needed now)
     */
    dateToSafeId(dateStr) {
        return dateStr;
    },

    /**
     * Convert any text to safe HTML ID by replacing non-alphanumeric characters with hyphens
     * Must match the Python safe_id filter implementation
     */
    safeId(text) {
        if (!text) return '';
        return String(text).replace(/[^a-zA-Z0-9]/g, '-');
    },

    /**
     * Format bytes into KB, MB, GB, TB, ensuring the numeric value is less than 1000.
     * Uses Italian locale for number formatting (space for thousands, comma for decimal).
     */
    formatBytes(bytes, decimals = 2) {
        if (bytes === null || bytes === undefined || isNaN(bytes)) return '';
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

        const i = Math.floor(Math.log(bytes) / Math.log(k));

        const num = parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
        
        // Format number with space as thousand separator and comma as decimal separator.
        const formattedNum = num.toLocaleString('it-IT', {
            minimumFractionDigits: dm,
            maximumFractionDigits: dm
        }).replace(/\./g, ' ');

        return formattedNum + ' ' + sizes[i];
    },

    /**
     * Applies byte formatting to all elements with data-bytes-to-format attribute.
     * Replaces the content of the element with the formatted byte string in parentheses.
     */
    applyByteFormatting() {
        document.querySelectorAll('[data-bytes-to-format]').forEach(el => {
            const bytes = parseInt(el.dataset.bytesToFormat, 10);
            if (!isNaN(bytes)) {
                el.textContent = '(' + this.formatBytes(bytes) + ')';
            }
        });
    }
  };

  // Namespace + global alias for backward compatibility
  AIQO.Core.ReportUtils = ReportUtils;
  window.ReportUtils = ReportUtils;
})();
