const numericValue = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  const parsed = Number(String(value ?? '').replace(/[^0-9.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
};

export const DASHBOARD_V4_VARIANTS = ['executive', 'analytical', 'operational'];

export const dashboardComponentRegistry = Object.freeze({
  hero: { columns: 4, emphasis: 'high' },
  featured: { columns: 12, emphasis: 'high' },
  balanced: { columns: 6, emphasis: 'medium' },
  dense: { columns: 4, emphasis: 'compact' },
  detail: { columns: 12, emphasis: 'low' },
});

const variantPalettes = {
  executive: ['#0f766e', '#7c3aed', '#d97706', '#2563eb', '#dc2626'],
  analytical: ['#2563eb', '#0891b2', '#7c3aed', '#059669', '#d97706'],
  operational: ['#d97706', '#2563eb', '#059669', '#dc2626', '#64748b'],
};

const sectionTitles = {
  operational: {
    overview: ['Operational pulse', 'ภาพรวมการดำเนินงาน'],
    monitor: ['Current movement', 'ความเคลื่อนไหวปัจจุบัน'],
    exceptions: ['Drivers and exceptions', 'ปัจจัยขับเคลื่อนและข้อยกเว้น'],
    records: ['Operational detail', 'รายละเอียดการดำเนินงาน'],
  },
  analytical: {
    overview: ['Analytical overview', 'ภาพรวมเชิงวิเคราะห์'],
    trends: ['How performance changed', 'ผลลัพธ์เปลี่ยนแปลงอย่างไร'],
    drivers: ['What explains the result', 'ปัจจัยที่อธิบายผลลัพธ์'],
    records: ['Evidence and detail', 'หลักฐานและรายละเอียด'],
  },
  executive: {
    overview: ['Executive summary', 'บทสรุปผู้บริหาร'],
    headline: ['The headline movement', 'ความเคลื่อนไหวสำคัญ'],
    drivers: ['Key business drivers', 'ปัจจัยขับเคลื่อนธุรกิจหลัก'],
    records: ['Supporting detail', 'รายละเอียดประกอบ'],
  },
};

const section = (variant, id, purpose, layout, widgetIds, kpiIndices = []) => {
  const [title] = sectionTitles[variant][id];
  return { id, title, purpose, layout, widget_ids: widgetIds, kpi_indices: kpiIndices };
};

export const dashboardSectionMessageKey = (item, variant = 'executive') => {
  const defaults = sectionTitles[variant]?.[item?.id];
  return defaults && item?.title === defaults[0]
    ? `section_${variant}_${item.id}`
    : null;
};

const makeSections = (widgets = [], kpis = [], variant = 'executive') => {
  const idsFor = (purposes) => widgets
    .filter((widget) => purposes.includes(widget.purpose || (widget.kind === 'table' ? 'detail' : 'comparison')))
    .map((widget) => widget.id);
  const trends = idsFor(['trend']);
  const drivers = idsFor(['ranking', 'comparison', 'distribution']);
  const details = idsFor(['detail']);
  const assigned = new Set([...trends, ...drivers, ...details]);
  const others = widgets.filter((widget) => !assigned.has(widget.id)).map((widget) => widget.id);
  if (variant === 'operational') {
    return [
      section(variant, 'overview', 'overview', 'hero', [], kpis.map((_, index) => index)),
      section(variant, 'monitor', 'trend', 'dense', [...trends, ...others]),
      section(variant, 'exceptions', 'drivers', 'dense', drivers),
      section(variant, 'records', 'detail', 'detail', details),
    ];
  }
  if (variant === 'analytical') {
    return [
      section(variant, 'overview', 'overview', 'hero', [], kpis.map((_, index) => index)),
      section(variant, 'trends', 'trend', 'balanced', trends),
      section(variant, 'drivers', 'drivers', 'balanced', [...drivers, ...others]),
      section(variant, 'records', 'detail', 'detail', details),
    ];
  }
  return [
    section(variant, 'overview', 'overview', 'hero', [], kpis.map((_, index) => index)),
    section(variant, 'headline', 'trend', 'featured', trends.slice(0, 1)),
    section(variant, 'drivers', 'drivers', 'balanced', [...drivers, ...trends.slice(1), ...others]),
    section(variant, 'records', 'detail', 'detail', details),
  ];
};

export const upgradeDashboardSpecV4 = (input = {}, requestedVariant) => {
  const spec = JSON.parse(JSON.stringify(input || {}));
  const widgets = Array.isArray(spec.widgets) ? spec.widgets : [];
  const kpis = Array.isArray(spec.kpis) ? spec.kpis : [];
  const variant = DASHBOARD_V4_VARIANTS.includes(requestedVariant)
    ? requestedVariant
    : DASHBOARD_V4_VARIANTS.includes(spec.presentation?.variant)
      ? spec.presentation.variant
      : 'executive';
  const widgetIds = new Set(widgets.map((widget) => widget.id));
  const widgetOrder = new Map(widgets.map((widget, index) => [widget.id, index]));
  const assigned = new Set();
  let sections = Array.isArray(spec.sections) ? spec.sections.map((rawSection, index) => {
    const sectionId = String(rawSection?.id || `section-${index}`);
    const defaultTitles = sectionTitles[variant]?.[sectionId];
    const title = String(rawSection?.title || defaultTitles?.[0] || 'Analysis');
    return {
      id: sectionId,
      title,
      subtitle: String(rawSection?.subtitle || ''),
      purpose: String(rawSection?.purpose || 'analysis'),
      layout: dashboardComponentRegistry[rawSection?.layout] ? rawSection.layout : 'balanced',
      widget_ids: (rawSection?.widget_ids || []).filter((id) => {
        if (!widgetIds.has(id) || assigned.has(id)) return false;
        assigned.add(id);
        return true;
      }).sort((left, right) => (widgetOrder.get(left) ?? 0) - (widgetOrder.get(right) ?? 0)),
      kpi_indices: (rawSection?.kpi_indices || []).filter((indexValue) => Number.isInteger(indexValue) && indexValue >= 0 && indexValue < kpis.length),
    };
  }) : [];
  if (!sections.length || requestedVariant) {
    sections = makeSections(widgets, kpis, variant);
  } else {
    const missing = widgets.filter((widget) => !assigned.has(widget.id));
    for (const widget of missing) {
      const purpose = widget.purpose || (widget.kind === 'table' ? 'detail' : 'drivers');
      const targetPurposes = purpose === 'detail'
        ? ['detail']
        : purpose === 'trend' ? ['trend'] : ['drivers', 'analysis'];
      let target = sections.find((section) => targetPurposes.includes(section.purpose));
      if (!target) {
        target = purpose === 'detail'
          ? { id: 'records', title: 'Supporting detail', purpose: 'detail', layout: 'detail', widget_ids: [], kpi_indices: [] }
          : { id: 'analysis', title: 'Analysis', purpose: purpose === 'trend' ? 'trend' : 'analysis', layout: 'balanced', widget_ids: [], kpi_indices: [] };
        sections.push(target);
      }
      target.widget_ids.push(widget.id);
    }
  }
  sections = sections.filter((section) => section.purpose === 'overview' || section.widget_ids.length || section.kpi_indices.length);
  return {
    ...spec,
    version: 4,
    widgets,
    kpis,
    presentation: {
      theme: 'editorial',
      density: variant === 'operational' ? 'compact' : 'comfortable',
      show_story: true,
      show_evidence: true,
      palette: variantPalettes[variant],
      ...(spec.presentation || {}),
      variant,
      ...(requestedVariant ? { palette: variantPalettes[variant] } : {}),
    },
    sections,
    story: {
      mode: 'evidence_grounded',
      tone: variant === 'executive' ? 'executive' : 'analytical',
      ...(spec.story || {}),
      chapter_order: sections.map((section) => section.id),
    },
  };
};

export const orderedDashboardWidgets = (spec = {}) => {
  const normalized = upgradeDashboardSpecV4(spec);
  const byId = new Map(normalized.widgets.map((widget) => [widget.id, widget]));
  return normalized.sections.flatMap((section) => section.widget_ids.map((id) => byId.get(id)).filter(Boolean));
};

export const filterDashboardRows = (rows, filters) =>
  (rows || []).filter((row) =>
    Object.entries(filters || {}).every(([field, selected]) => {
      if (selected == null || selected === '') return true;
      return String(row[field] ?? '') === String(selected);
    }),
  );

export const computeKpiValue = (rows, kpi) => {
  if (kpi.kind === 'count') return rows.length;
  const values = rows.map((row) => numericValue(row[kpi.field]));
  if (kpi.kind === 'average') {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }
  return values.reduce((sum, value) => sum + value, 0);
};

export const aggregateWidgetRows = (rows, widget) => {
  const dimension = widget.dimension;
  if (!dimension) return [];
  const groups = new Map();
  for (const row of rows) {
    const key = String(row[dimension] ?? '—');
    const current = groups.get(key) || { total: 0, count: 0 };
    current.total += widget.aggregation === 'count'
      ? 1
      : numericValue(row[widget.measure]);
    current.count += 1;
    groups.set(key, current);
  }
  const valueKey = widget.measure || 'count';
  const result = [...groups.entries()].map(([name, value]) => ({
    name,
    [valueKey]: widget.aggregation === 'average'
      ? value.total / Math.max(1, value.count)
      : value.total,
  }));
  result.sort((a, b) => numericValue(b[valueKey]) - numericValue(a[valueKey]));
  return result.slice(0, widget.limit || 30);
};

export const buildParetoRows = (rows = [], valueKey = 'value') => {
  const total = rows.reduce((sum, row) => sum + Math.abs(numericValue(row?.[valueKey])), 0);
  let cumulative = 0;
  return rows.map((row) => {
    cumulative += Math.abs(numericValue(row?.[valueKey]));
    return {
      ...row,
      cumulativePercentage: total ? (cumulative / total) * 100 : 0,
    };
  });
};

export const formatDashboardValue = (value, locale = 'th', format = 'auto', currency = 'THB') => {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? '—');
  const localeName = locale === 'en' ? 'en-US' : 'th-TH';
  if (format === 'currency') {
    return new Intl.NumberFormat(localeName, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(number);
  }
  if (format === 'percent') {
    return new Intl.NumberFormat(localeName, {
      style: 'percent',
      maximumFractionDigits: 2,
    }).format(number);
  }
  return new Intl.NumberFormat(locale === 'en' ? 'en-US' : 'th-TH', {
    notation: format === 'compact' || (format === 'auto' && Math.abs(number) >= 1_000_000)
      ? 'compact'
      : 'standard',
    maximumFractionDigits: 2,
  }).format(number);
};

export const dashboardFieldGroups = (schema = []) => ({
  dimensions: schema.filter((column) => ['text', 'date'].includes(column.kind)),
  measures: schema.filter((column) => column.kind === 'number'),
});

export const CORE_CHART_TYPES = ['bar', 'line', 'area', 'pie', 'pareto'];
export const CHART_WELLS = ['axis', 'values'];
export const COUNT_FIELD = '*';

export const normalizeChartWell = (well) => {
  const value = String(well || '').trim().toLowerCase();
  if (['x', 'xaxis', 'x-axis', 'axis', 'category'].includes(value)) return 'axis';
  if (['y', 'yaxis', 'y-axis', 'values', 'value', 'measure'].includes(value)) return 'values';
  return null;
};

export const chartColumnMeta = (schema = [], name) => (
  (schema || []).find((column) => column.name === name) || null
);

export const chartFormula = (widget = {}) => {
  if (widget.kind === 'table') {
    const columns = (widget.columns || []).join(', ');
    return columns ? `SELECT ${columns}` : 'SELECT *';
  }
  const dimension = widget.dimension || '—';
  if (widget.aggregation === 'count' || !widget.measure) {
    return `COUNT(*) GROUP BY ${dimension}`;
  }
  const fn = widget.aggregation === 'average' ? 'AVG' : 'SUM';
  return `${fn}(${widget.measure}) GROUP BY ${dimension}`;
};

export const bindChartField = (widget = {}, well, column, schema = [], aggregation) => {
  if ((widget.kind || 'chart') === 'table') {
    return { widget, error: 'not_a_chart' };
  }
  const resolvedWell = normalizeChartWell(well);
  if (!resolvedWell) {
    return { widget, error: 'unknown_well' };
  }
  const next = { ...widget, kind: 'chart' };
  if (resolvedWell === 'axis') {
    const meta = chartColumnMeta(schema, column);
    if (!meta || !['text', 'date'].includes(meta.kind)) {
      return { widget, error: 'axis_needs_dimension' };
    }
    const isDate = meta.kind === 'date';
    return {
      widget: {
        ...next,
        dimension: meta.name,
        time_grain: isDate ? (next.time_grain || 'month') : null,
        cross_filter: !isDate,
        purpose: isDate ? 'trend' : (next.purpose === 'trend' ? 'ranking' : next.purpose),
      },
      error: null,
    };
  }
  if (column === COUNT_FIELD) {
    return {
      widget: {
        ...next,
        aggregation: 'count',
        measure: null,
      },
      error: null,
    };
  }
  const meta = chartColumnMeta(schema, column);
  if (!meta || meta.kind !== 'number') {
    return { widget, error: 'values_needs_measure' };
  }
  const nextAggregation = aggregation && aggregation !== 'count'
    ? aggregation
    : (next.aggregation === 'count' ? 'sum' : (next.aggregation || 'sum'));
  return {
    widget: {
      ...next,
      measure: meta.name,
      aggregation: nextAggregation,
    },
    error: null,
  };
};

export const unbindChartField = (widget = {}, well) => {
  const resolvedWell = normalizeChartWell(well);
  if (resolvedWell === 'axis') {
    return { ...widget, dimension: '', time_grain: null };
  }
  if (resolvedWell === 'values') {
    return { ...widget, measure: null, aggregation: 'count' };
  }
  return widget;
};

export const inspectChart = (widget = {}, schema = [], extras = {}) => {
  const axis = chartColumnMeta(schema, widget.dimension);
  const values = widget.aggregation === 'count' || !widget.measure
    ? { field: COUNT_FIELD, kind: 'count', aggregation: 'count' }
    : {
      field: widget.measure,
      kind: chartColumnMeta(schema, widget.measure)?.kind || 'number',
      aggregation: widget.aggregation || 'sum',
    };
  const sourceColumns = [widget.dimension, widget.measure].filter(Boolean);
  return {
    widget_id: widget.id || null,
    kind: widget.kind || 'chart',
    chart_type: widget.chart_type || 'bar',
    title: widget.title || '',
    wells: {
      axis: widget.dimension
        ? { field: widget.dimension, kind: axis?.kind || 'text' }
        : null,
      values,
      x: widget.dimension
        ? { field: widget.dimension, kind: axis?.kind || 'text' }
        : null,
      y: values,
    },
    formula: chartFormula(widget),
    engine: 'duckdb',
    time_grain: widget.time_grain || null,
    limit: widget.limit || 20,
    source_columns: sourceColumns,
    row_count: extras.row_count ?? null,
    filtered_row_count: extras.filtered_row_count ?? null,
    point_count: extras.point_count ?? null,
  };
};

export const reorderDashboardWidgets = (widgets = [], sourceId, targetId) => {
  const sourceIndex = widgets.findIndex((widget) => widget.id === sourceId);
  const targetIndex = widgets.findIndex((widget) => widget.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return widgets;
  const next = [...widgets];
  const [moved] = next.splice(sourceIndex, 1);
  next.splice(targetIndex, 0, moved);
  return next;
};

export const makeDashboardWidget = (schema = [], kind = 'chart', locale = 'en') => {
  const { dimensions, measures } = dashboardFieldGroups(schema);
  const dimension = dimensions[0]?.name || schema[0]?.name || '';
  const measure = measures[0]?.name || '';
  const id = `widget-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  if (kind === 'table') {
    return {
      id,
      kind: 'table',
      title: locale === 'th' ? 'รายละเอียด' : 'Detail',
      columns: schema.slice(0, 8).map((column) => column.name),
      span: 12,
      purpose: 'detail',
    };
  }
  return {
    id,
    kind: 'chart',
    chart_type: 'bar',
    title: measure ? `${measure} by ${dimension}` : `Count by ${dimension}`,
    dimension,
    measure: measure || null,
    aggregation: measure ? 'sum' : 'count',
    time_grain: dimensions.find((column) => column.name === dimension)?.kind === 'date'
      ? 'month'
      : null,
    limit: 20,
    span: 6,
    cross_filter: dimensions.find((column) => column.name === dimension)?.kind !== 'date',
    purpose: dimensions.find((column) => column.name === dimension)?.kind === 'date'
      ? 'trend'
      : 'ranking',
  };
};

export const makeDashboardKpi = (schema = [], locale = 'en') => {
  const measure = schema.find((column) => column.kind === 'number')?.name;
  return measure
    ? { kind: 'sum', field: measure, label: locale === 'th' ? `รวม ${measure}` : `Total ${measure}`, format: 'auto', currency: 'THB' }
    : { kind: 'count', field: null, label: locale === 'th' ? 'จำนวนแถว' : 'Rows', format: 'auto' };
};
