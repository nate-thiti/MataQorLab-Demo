import { describe, expect, it } from 'vitest';
import { buildPinFromChatMessage, packetLifecycleLabel } from './decisionPacket.js';

describe('decisionPacket helpers', () => {
  it('builds an evidence-linked pin from a chat message', () => {
    const pin = buildPinFromChatMessage({
      message: {
        id: '11111111-1111-4111-8111-111111111111',
        content: 'Branch A leads revenue.',
        verification: { status: 'grounded' },
        analysisAudit: { claims: [{ text: 'Branch A is #1' }, 'Keep monitoring'] },
      },
      chartData: { chart_type: 'bar', config: { title: 'Revenue by branch' } },
      conversationId: '22222222-2222-4222-8222-222222222222',
      sourceMessageId: '11111111-1111-4111-8111-111111111111',
    });

    expect(pin.kind).toBe('chart');
    expect(pin.verification_status).toBe('grounded');
    expect(pin.claims).toEqual(['Branch A is #1', 'Keep monitoring']);
    expect(pin.source_message_id).toContain('1111');
  });

  it('labels packet lifecycle for th/en', () => {
    expect(packetLifecycleLabel('stale', true)).toBe('Needs re-prove');
    expect(packetLifecycleLabel('proved', false)).toBe('พิสูจน์แล้ว');
  });
});
