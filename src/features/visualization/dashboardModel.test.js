import { describe, expect, it } from 'vitest';
import {
  aggregateWidgetRows,
  bindChartField,
  buildParetoRows,
  computeKpiValue,
  filterDashboardRows,
  formatDashboardValue,
  dashboardSectionMessageKey,
  inspectChart,
  makeDashboardWidget,
  orderedDashboardWidgets,
  reorderDashboardWidgets,
  upgradeDashboardSpecV4,
} from './dashboardModel.js';

const rows = [
  { branch: 'A', revenue: 10 },
  { branch: 'A', revenue: 15 },
  { branch: 'B', revenue: 7 },
];

describe('adaptive dashboard model', () => {
  it('applies report-scoped slicers', () => {
    expect(filterDashboardRows(rows, { branch: 'A' })).toHaveLength(2);
  });

  it('recomputes KPI values after filtering', () => {
    const filtered = filterDashboardRows(rows, { branch: 'A' });
    expect(computeKpiValue(filtered, { kind: 'sum', field: 'revenue' })).toBe(25);
  });

  it('aggregates chart widgets by their dynamic fields', () => {
    expect(aggregateWidgetRows(rows, {
      dimension: 'branch',
      measure: 'revenue',
      aggregation: 'sum',
    })).toEqual([
      { name: 'A', revenue: 25 },
      { name: 'B', revenue: 7 },
    ]);
  });

  it('builds deterministic cumulative percentages for Pareto rendering', () => {
    expect(buildParetoRows([
      { name: 'A', value: 60 },
      { name: 'B', value: 30 },
      { name: 'C', value: 10 },
    ])).toEqual([
      { name: 'A', value: 60, cumulativePercentage: 60 },
      { name: 'B', value: 30, cumulativePercentage: 90 },
      { name: 'C', value: 10, cumulativePercentage: 100 },
    ]);
  });

  it('reorders widgets without mutating the original list', () => {
    const widgets = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    expect(reorderDashboardWidgets(widgets, 'c', 'a').map((item) => item.id))
      .toEqual(['c', 'a', 'b']);
    expect(widgets.map((item) => item.id)).toEqual(['a', 'b', 'c']);
  });

  it('binds Power BI-style field wells and exposes an inspectable formula', () => {
    const schema = [
      { name: 'branch', kind: 'text' },
      { name: 'revenue', kind: 'number' },
    ];
    const bound = bindChartField(
      { kind: 'chart', chart_type: 'bar' },
      'axis',
      'branch',
      schema,
    );
    const valued = bindChartField(bound.widget, 'values', 'revenue', schema, 'sum');
    expect(valued.error).toBeNull();
    expect(inspectChart(valued.widget, schema)).toMatchObject({
      formula: 'SUM(revenue) GROUP BY branch',
      engine: 'duckdb',
      wells: {
        axis: { field: 'branch', kind: 'text' },
        values: { field: 'revenue', aggregation: 'sum' },
        x: { field: 'branch', kind: 'text' },
        y: { field: 'revenue', aggregation: 'sum' },
      },
    });
    expect(bindChartField(valued.widget, 'x', 'revenue', schema).error)
      .toBe('axis_needs_dimension');
    const renamed = { ...valued.widget, title: 'Revenue by branch' };
    expect(bindChartField(renamed, 'y', 'revenue', schema).widget.title)
      .toBe('Revenue by branch');
  });

  it('creates a safe editable widget from schema roles', () => {
    const widget = makeDashboardWidget([
      { name: 'branch', kind: 'text' },
      { name: 'revenue', kind: 'number' },
    ]);
    expect(widget).toMatchObject({
      kind: 'chart',
      dimension: 'branch',
      measure: 'revenue',
      aggregation: 'sum',
      cross_filter: true,
    });
  });

  it('formats dashboard values using user-selected presentation', () => {
    expect(formatDashboardValue(0.125, 'en', 'percent')).toBe('12.5%');
    expect(formatDashboardValue(1500000, 'en', 'compact')).toContain('1.5');
  });

  it('upgrades a flat V3 dashboard into section-based V4 without losing widgets', () => {
    const upgraded = upgradeDashboardSpecV4({
      version: 3,
      kpis: [{ kind: 'count', label: 'Rows' }],
      widgets: [
        { id: 'trend', kind: 'chart', purpose: 'trend' },
        { id: 'ranking', kind: 'chart', purpose: 'ranking' },
        { id: 'detail', kind: 'table', purpose: 'detail' },
      ],
    });

    expect(upgraded.version).toBe(4);
    expect(upgraded.presentation.variant).toBe('executive');
    expect(upgraded.story.mode).toBe('evidence_grounded');
    expect(orderedDashboardWidgets(upgraded).map((widget) => widget.id))
      .toEqual(['trend', 'ranking', 'detail']);
  });

  it('can recompose the same verified widgets for another V4 presentation variant', () => {
    const operational = upgradeDashboardSpecV4({
      widgets: [
        { id: 'trend', kind: 'chart', purpose: 'trend' },
        { id: 'ranking', kind: 'chart', purpose: 'ranking' },
      ],
      kpis: [],
    }, 'operational');

    expect(operational.presentation.variant).toBe('operational');
    expect(operational.sections.some((section) => section.id === 'monitor')).toBe(true);
    expect(new Set(orderedDashboardWidgets(operational).map((widget) => widget.id)))
      .toEqual(new Set(['trend', 'ranking']));
    const monitor = operational.sections.find((section) => section.id === 'monitor');
    expect(dashboardSectionMessageKey(monitor, 'operational'))
      .toBe('section_operational_monitor');
  });

  it('resolves a legacy default section through the central i18n message key', () => {
    const upgraded = upgradeDashboardSpecV4({
      version: 4,
      presentation: { variant: 'executive' },
      widgets: [{ id: 'trend', kind: 'chart', purpose: 'trend' }],
      sections: [{
        id: 'headline',
        title: 'The headline movement',
        purpose: 'trend',
        layout: 'featured',
        widget_ids: ['trend'],
      }],
    });

    expect(dashboardSectionMessageKey(upgraded.sections[0], 'executive'))
      .toBe('section_executive_headline');
    expect(upgraded.sections[0].widget_ids).toEqual(['trend']);
  });
});
