import { describe, expect, it } from 'vitest';
import {
  followUpPrompts,
  lastAssistantMessageIndex,
  messageActionKey,
  uniqueMessageKeys,
} from './chatInteractions.js';

describe('chat interactions', () => {
  it('finds the latest assistant response', () => {
    expect(lastAssistantMessageIndex([
      { role: 'user' },
      { role: 'ai' },
      { role: 'user' },
    ])).toBe(1);
  });

  it('uses stable IDs when available', () => {
    expect(messageActionKey({ id: 'message-1', role: 'ai' }, 4)).toBe('message-1');
    expect(messageActionKey({ role: 'user' }, 2)).toBe('user-2');
  });

  it('creates unique render keys when transient copies share a database id', () => {
    expect(uniqueMessageKeys([
      { id: 'message-1', role: 'user' },
      { id: 'message-1', role: 'user' },
      { id: 'message-2', role: 'ai' },
    ])).toEqual([
      'message-1:copy:1',
      'message-1:copy:2',
      'message-2',
    ]);
  });

  it('offers evidence-aware bilingual follow-ups', () => {
    expect(followUpPrompts({ verification: { status: 'grounded' } }, true)[1])
      .toBe('Show the evidence behind this');
    expect(followUpPrompts({}, false)).toEqual([
      'อธิบายให้ง่ายขึ้นอีกหน่อย',
      'ยกตัวอย่างโดยอิงจากคำถามล่าสุดของฉัน',
      'สรุปเป็น Checklist ที่ลงมือทำได้',
    ]);
  });

  it('adapts analysis follow-ups to both user and assistant messages', () => {
    const messages = [
      { role: 'user', content: 'ช่วยวิเคราะห์ยอดขายแต่ละสาขา' },
      { role: 'ai', content: 'สาขา A มียอดขายสูงสุด แต่แนวโน้มลดลง' },
    ];

    expect(followUpPrompts(messages[1], false, undefined, {
      messages,
      messageIndex: 1,
    })).toEqual([
      'อะไรคือสาเหตุหลักของความแตกต่างนี้?',
      'แยกผลลัพธ์นี้ตามสาขา',
      'เปลี่ยนข้อค้นพบนี้เป็น 3 สิ่งที่ควรลงมือทำ',
    ]);
  });

  it('prioritizes source-aware prompts after web research', () => {
    const prompts = followUpPrompts({
      content: 'Latest market update',
      webSources: [{ url: 'https://example.com' }],
    }, true);

    expect(prompts).toContain('Show which sources support each claim');
    expect(prompts).toContain('How could this affect my business?');
  });

  it('suggests pin-first follow-ups for visualization responses', () => {
    const prompts = followUpPrompts({
      content: '{"action":"render_chart","chart_type":"bar"}',
    }, true);

    expect(prompts[0]).toBe('Pin this finding to my decision packet');
    expect(prompts).toContain('Drill into the most unusual point in this chart');
  });
});
