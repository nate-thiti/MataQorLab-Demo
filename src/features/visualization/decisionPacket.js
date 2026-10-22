export function buildPinFromChatMessage({
  message,
  chartData,
  reportData,
  summary,
  conversationId,
  sourceMessageId,
  title,
}) {
  const verification = message?.verification || reportData?.verification || null;
  const claims = Array.isArray(message?.analysisAudit?.claims)
    ? message.analysisAudit.claims.map((claim) => (
      typeof claim === 'string' ? claim : (claim?.text || claim?.claim || '')
    )).filter(Boolean).slice(0, 8)
    : [];
  return {
    kind: chartData ? 'chart' : (reportData ? 'report' : 'finding'),
    title: title || chartData?.config?.title || reportData?.title || 'Pinned finding',
    summary: String(reportData?.summary || summary || message?.content || '').slice(0, 4000),
    source_message_id: sourceMessageId || message?.id || null,
    conversation_id: conversationId || null,
    verification_status: verification?.status || null,
    verification: verification || {},
    claims,
    evidence: {
      verification,
      analysis_audit: message?.analysisAudit || null,
      chart_type: chartData?.chart_type || null,
      web_sources: message?.webSources || [],
    },
    formula: chartData?.config?.formula || null,
  };
}

export function packetLifecycleLabel(lifecycle, isEn = false) {
  const value = String(lifecycle || 'draft');
  if (isEn) {
    return ({
      draft: 'Draft',
      proved: 'Proved',
      stale: 'Needs re-prove',
      final: 'Final',
    })[value] || value;
  }
  return ({
    draft: 'ฉบับร่าง',
    proved: 'พิสูจน์แล้ว',
    stale: 'ต้องพิสูจน์ใหม่',
    final: 'ฉบับสมบูรณ์',
  })[value] || value;
}
