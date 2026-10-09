const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jsRoot = path.join(__dirname, '../../src/aiqo_pg_ai_report/report_templates/static/js');

function loadChart(data) {
  const context = { reportData: data, Chart: { defaults: { font: {} } } };
  context.window = context;
  vm.createContext(context);
  for (const file of ['report-utils.js', 'charts/annotation-service.js', 'charts/chart-factory.js']) {
    vm.runInContext(fs.readFileSync(path.join(jsRoot, file), 'utf8'), context);
  }
  const source = fs.readFileSync(path.join(jsRoot, 'components/query-details.js'), 'utf8');
  const start = source.indexOf('  function buildAllExecutionsForCode(');
  const end = source.indexOf('  function renderQueryChart(', start);
  vm.runInContext(source.slice(start, end), context);
  return context;
}

function verifySeries(data, first, second, expectedCount) {
  const context = loadChart(data);
  const a = context.buildAllExecutionsForCode(first);
  const b = context.buildAllExecutionsForCode(second);
  assert.equal(JSON.stringify(a), JSON.stringify(b));
  assert.equal(a.filter(e => e.targetIndex !== null).length, expectedCount);
  const targets = a.map(e => ({ day: e.day, index: e.targetIndex }));
  const factory = new context.AIQO.Core.ChartFactory(data);
  const processed = factory._processExecutionData(a);
  assert.deepEqual(a.map(e => ({ day: e.day, index: e.targetIndex })), targets);
  for (let i = 0; i < a.length; i++) {
    if (a[i].targetIndex === null) {
      assert.equal(processed.durations[i], null);
      continue;
    }
    const original = data.reports.by_day[a[i].day][a[i].targetIndex];
    assert.equal(processed.durations[i], original.duration / 3600000);
    assert.ok(processed.labels[i].includes('T'));
    assert.ok(!processed.labels[i].includes(' CES'));
  }
  return { a, processed };
}

test('all occurrences share a chronologically ordered series and retain exact navigation targets', () => {
  const early = { code: 'same', query_timestamp: '2026-09-30 09:11:55 CES', duration: 5658386.812 };
  const late = { code: 'same', query_timestamp: '2026-09-30 21:36:09 CES', duration: 2667310.055 };
  const next = { code: 'same', query_timestamp: '2026-10-01 08:00:00 CES', duration: 1000 };
  const data = {
    charts: { all_dates: ['2026-10-02', '2026-10-01', '2026-09-30'] },
    reports: { by_day: {
      '2026-09-30': [late, { code: 'other' }, early],
      '2026-10-01': [next],
      '2026-10-02': [],
    } },
  };
  const { a, processed } = verifySeries(data, early, late, 3);
  assert.deepEqual(Array.from(a, e => e.targetIndex), [2, 0, 0, null]);
  assert.deepEqual(Array.from(processed.labels), [
    '2026-09-30T09:11:55', '2026-09-30T21:36:09', '2026-10-01T08:00:00', '2026-10-02',
  ]);
});

if (process.env.AIQO_REGRESSION_REPORT) {
  test('uploaded RCA report includes both batches and all eleven executions', () => {
    const html = fs.readFileSync(process.env.AIQO_REGRESSION_REPORT, 'utf8');
    const data = JSON.parse(html.split('const reportData = ')[1].split(';\n')[0]);
    const matches = data.reports.by_day['2026-09-30'].filter(r => r.code.startsWith('0C95B2'));
    assert.equal(matches.length, 2);
    const { processed } = verifySeries(data, matches[0], matches[1], 11);
    assert.ok(processed.labels.includes('2026-09-30T09:11:55'));
    assert.ok(processed.labels.includes('2026-09-30T21:36:09'));
  });
}
