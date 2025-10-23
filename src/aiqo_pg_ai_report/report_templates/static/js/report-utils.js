/**
 * Utility functions for the report
 */
const ReportUtils = {
    /**
     * Generate a random RGB color
     */
    getRandomColor() {
        const r = Math.floor(Math.random() * 255);
        const g = Math.floor(Math.random() * 255);
        const b = Math.floor(Math.random() * 255);
        return `rgb(${r}, ${g}, ${b})`;
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
    }
};
