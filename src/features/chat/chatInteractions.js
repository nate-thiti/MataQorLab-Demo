export function messageActionKey(message, index) {
  return message?.id || `${message?.role || 'message'}-${index}`;
}

/**
 * Preserve the database id for normal rows while making transient duplicate
 * copies safe to render during optimistic/snapshot reconciliation.
 */
export function uniqueMessageKeys(messages) {
  if (!Array.isArray(messages)) return [];
  const totals = new Map();
  messages.forEach((message, index) => {
    const base = messageActionKey(message, index);
    totals.set(base, (totals.get(base) || 0) + 1);
  });
  const seen = new Map();
  return messages.map((message, index) => {
    const base = messageActionKey(message, index);
    if ((totals.get(base) || 0) === 1) return base;
    const occurrence = (seen.get(base) || 0) + 1;
    seen.set(base, occurrence);
    return `${base}:copy:${occurrence}`;
  });
}

export function lastAssistantMessageIndex(messages) {
  if (!Array.isArray(messages)) return -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'ai') return index;
  }
  return -1;
}

function latestUserText(messages, messageIndex) {
  if (!Array.isArray(messages)) return '';
  const start = Number.isInteger(messageIndex) ? messageIndex - 1 : messages.length - 1;
  for (let index = start; index >= 0; index -= 1) {
    if (messages[index]?.role === 'user') return String(messages[index]?.content || '');
  }
  return '';
}

function uniquePrompts(prompts) {
  return [...new Set(prompts.filter(Boolean))].slice(0, 3);
}

export function followUpPrompts(
  message,
  isEn = false,
  translate = (_key, fallback) => fallback,
  context = {},
) {
  const evidenceAware = message?.verification || message?.analysisAudit;
  const userText = latestUserText(context.messages, context.messageIndex);
  const assistantText = String(message?.content || '');
  const combined = `${userText}\n${assistantText}`.toLowerCase();
  const hasWebSources = Boolean(message?.webSources?.length || message?.searchQueries?.length);
  const hasVisualization = /"action"\s*:\s*"(?:render_chart|propose_visualization|generate_report)"/i
    .test(assistantText);
  const hasComparison = /(compare|comparison|versus|\bvs\.?\b|trend|เปรียบเทียบ|เทียบกับ|แนวโน้ม)/i
    .test(combined);
  const hasAnalysis = Boolean(
    message?.verification
    || message?.analysisAudit
    || message?.cleaningReport
    || /(sales|revenue|profit|cost|kpi|metric|ยอดขาย|รายได้|กำไร|ต้นทุน|ตัวชี้วัด)/i.test(combined),
  );
  const dimension = [
    [/(branch|store|สาขา)/i, isEn ? 'branch' : 'สาขา'],
    [/(product|sku|สินค้า)/i, isEn ? 'product' : 'สินค้า'],
    [/(customer|ลูกค้า)/i, isEn ? 'customer segment' : 'กลุ่มลูกค้า'],
    [/(channel|ช่องทาง)/i, isEn ? 'channel' : 'ช่องทาง'],
  ].find(([pattern]) => pattern.test(combined))?.[1];

  if (hasVisualization) {
    return uniquePrompts(isEn ? [
      translate('chat.interactions.follow_up_pin_finding', 'Pin this finding to my decision packet'),
      translate('chat.interactions.follow_up_chart_drilldown', 'Drill into the most unusual point in this chart'),
      translate('chat.interactions.follow_up_compare_periods', 'Compare this with the previous period'),
      translate('chat.interactions.follow_up_actions', 'Turn these findings into 3 concrete actions'),
    ] : [
      translate('chat.interactions.follow_up_pin_finding', 'ปักข้อค้นพบนี้เข้า Decision packet'),
      translate('chat.interactions.follow_up_chart_drilldown', 'เจาะลึกจุดที่ผิดปกติที่สุดในกราฟนี้'),
      translate('chat.interactions.follow_up_compare_periods', 'เปรียบเทียบผลลัพธ์นี้กับช่วงก่อนหน้า'),
      translate('chat.interactions.follow_up_actions', 'เปลี่ยนข้อค้นพบนี้เป็น 3 สิ่งที่ควรลงมือทำ'),
    ]);
  }

  if (hasAnalysis && !hasWebSources) {
    const comparisonPrompt = hasComparison
      ? (isEn
        ? translate('chat.interactions.follow_up_difference_driver', 'What are the main drivers of this difference?')
        : translate('chat.interactions.follow_up_difference_driver', 'อะไรคือสาเหตุหลักของความแตกต่างนี้?'))
      : (isEn
        ? translate('chat.interactions.follow_up_compare_periods', 'Compare this with the previous period')
        : translate('chat.interactions.follow_up_compare_periods', 'เปรียบเทียบผลลัพธ์นี้กับช่วงก่อนหน้า'));
    const breakdownPrompt = dimension
      ? (isEn
        ? `Break this result down by ${dimension}`
        : `แยกผลลัพธ์นี้ตาม${dimension}`)
      : (isEn
        ? translate('chat.interactions.follow_up_segments', 'Which segments contribute most to this result?')
        : translate('chat.interactions.follow_up_segments', 'กลุ่มไหนมีผลต่อผลลัพธ์นี้มากที่สุด?'));
    return uniquePrompts([
      comparisonPrompt,
      evidenceAware
        ? translate(
          'chat.interactions.follow_up_evidence',
          isEn ? 'Show the evidence behind this' : 'แสดงหลักฐานที่ใช้สรุปนี้',
        )
        : breakdownPrompt,
      isEn
        ? translate('chat.interactions.follow_up_actions', 'Turn these findings into 3 concrete actions')
        : translate('chat.interactions.follow_up_actions', 'เปลี่ยนข้อค้นพบนี้เป็น 3 สิ่งที่ควรลงมือทำ'),
    ]);
  }

  if (hasWebSources) {
    return uniquePrompts(isEn ? [
      translate('chat.interactions.follow_up_latest_sources', 'Summarize only the newest evidence'),
      translate('chat.interactions.follow_up_evidence', 'Show which sources support each claim'),
      translate('chat.interactions.follow_up_business_impact', 'How could this affect my business?'),
    ] : [
      translate('chat.interactions.follow_up_latest_sources', 'สรุปเฉพาะหลักฐานล่าสุด'),
      translate('chat.interactions.follow_up_evidence', 'บอกว่าแต่ละข้อสรุปอ้างอิงจากแหล่งใด'),
      translate('chat.interactions.follow_up_business_impact', 'ข้อมูลนี้อาจกระทบธุรกิจของฉันอย่างไร?'),
    ]);
  }

  return uniquePrompts(isEn ? [
    translate('chat.interactions.follow_up_simple', 'Explain that more simply'),
    translate('chat.interactions.follow_up_context_example', 'Give an example based on my latest question'),
    translate('chat.interactions.follow_up_checklist', 'Turn this into an actionable checklist'),
  ] : [
    translate('chat.interactions.follow_up_simple', 'อธิบายให้ง่ายขึ้นอีกหน่อย'),
    translate('chat.interactions.follow_up_context_example', 'ยกตัวอย่างโดยอิงจากคำถามล่าสุดของฉัน'),
    translate('chat.interactions.follow_up_checklist', 'สรุปเป็น Checklist ที่ลงมือทำได้'),
  ]);
}
