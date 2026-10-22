import { describe, expect, it } from 'vitest';
import {
  cleanMsgContent,
  fixMarkdownTables,
  sanitizeChatMessage,
} from './messageContent.js';
import { parseMarkdownToBlocks } from './markdownBlocks.js';

describe('sanitizeChatMessage web source history', () => {
  it('restores persisted snake_case sources for the chat UI', () => {
    const source = {
      title: 'Bank source',
      url: 'https://example.com/fx',
      snippet: 'Latest rate',
    };
    const message = sanitizeChatMessage({
      role: 'ai',
      content: 'Insight',
      web_sources: [source],
    });

    expect(message.webSources).toEqual([source]);
  });
});

describe('sanitizeChatMessage analysis audit history', () => {
  it('restores the audit packet from response metadata', () => {
    const audit = { audit_id: 'audit_123', findings: [{ id: 'f_1' }] };
    const message = sanitizeChatMessage({
      role: 'ai',
      content: 'Insight',
      response_metadata: { analysis_audit: audit },
    });

    expect(message.analysisAudit).toEqual(audit);
  });
});

describe('sanitizeChatMessage attachment history', () => {
  it('restores a user attachment from response metadata', () => {
    expect(sanitizeChatMessage({
      role: 'user',
      content: 'analyze',
      response_metadata: {
        attachment: 'sales.xlsx',
        column_mapping: { revenue: 'amount' },
        cleaning_recipe: { apply: true },
        cleaning_profile: 'standard',
        connection: {
          id: 'api-1',
          type: 'api',
          mapping: { revenue: 'amount' },
        },
      },
    })).toMatchObject({
      role: 'user',
      attachment: 'sales.xlsx',
      attachmentMapping: { revenue: 'amount' },
      attachmentCleaningRecipe: { apply: true },
      attachmentCleaningProfile: 'standard',
      connectionContext: {
        id: 'api-1',
        type: 'api',
        mapping: { revenue: 'amount' },
      },
    });
  });

  it('restores the workflow-answer marker used to hide setup replies', () => {
    const resolution = { decision_key: 'mapping:invoice', value: 'order_id' };

    expect(sanitizeChatMessage({
      role: 'user',
      content: 'Order ID',
      response_metadata: { orchestration_resolution: resolution },
    }).workflowResolution).toEqual(resolution);
  });
});

describe('AI display normalization', () => {
  it('removes internal context markup while preserving useful content', () => {
    const content = [
      '<calculated_metrics> External Web Context (pre-fetched by platform):',
      '- อุณหภูมิ 32-34°C',
      '</calculated_metrics>',
      '<web_sources>',
      '- กรมอุตุนิยมวิทยา: https://www.tmd.go.th',
      '</web_sources>',
    ].join('\n');

    const cleaned = cleanMsgContent(content);

    expect(cleaned).not.toContain('<calculated_metrics>');
    expect(cleaned).not.toContain('<web_sources>');
    expect(cleaned).not.toContain('pre-fetched by platform');
    expect(cleaned).toContain('อุณหภูมิ 32-34°C');
    expect(cleaned).toContain('https://www.tmd.go.th');
  });

  it('keeps markdown separators and drops colon-only junk rows', () => {
    const raw = [
      '| มิติ | สัดส่วน |',
      '| :--- | ---: |',
      '| : | : |',
      '| คลังสินค้า | +89.7% |',
    ].join('\n');
    const fixed = fixMarkdownTables(raw);
    const table = parseMarkdownToBlocks(fixed).find((block) => block.type === 'table');

    expect(fixed).toContain('| :--- | ---: |');
    expect(table.rows).toEqual([['คลังสินค้า', '+89.7%']]);
    expect(table.aligns).toEqual(['left', 'right']);
  });

  it('formats common section labels as headings', () => {
    expect(cleanMsgContent('ข้อเสนอแนะ:\n1. ตรวจสอบข้อมูล')).toContain(
      '### ข้อเสนอแนะ',
    );
  });
});
