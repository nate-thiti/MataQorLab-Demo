export function visualizationContextForRequest(
  visualizationContext,
  { attachedFileName = null, connectionId = null, ignore = false } = {},
) {
  if (!visualizationContext?.reportId || ignore) return null;
  const reportSource = visualizationContext.sourceConfig || {};
  if (
    (attachedFileName && attachedFileName !== reportSource.file_name)
    || (connectionId && connectionId !== reportSource.connection_id)
  ) return null;
  return {
    report_id: visualizationContext.reportId,
    widget_id: visualizationContext.widgetId || null,
    filters: visualizationContext.filters || {},
  };
}
