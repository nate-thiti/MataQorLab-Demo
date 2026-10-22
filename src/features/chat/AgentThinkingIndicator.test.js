import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AgentThinkingIndicator from './AgentThinkingIndicator';

describe('AgentThinkingIndicator', () => {
  it('shows bouncing dots and elapsed time without a framed status chip', () => {
    const html = renderToStaticMarkup(
      React.createElement(AgentThinkingIndicator, {
        elapsedSec: 12,
        isEn: false,
        stage: 'loading_data',
        detail: { file: 'abc_sales.xlsx' },
        t: (_key, fallback) => fallback,
      }),
    );

    expect(html).toContain('12 วินาที');
    expect(html).toContain('animate-bounce');
    expect(html).toMatch(/aria-label="กำลังโหลด sales\.xlsx…? 12 วินาที"/);
    expect(html).not.toContain('animate-spin');
    expect(html).not.toContain('border-stone');
    expect(html).not.toContain('กำลังโหลด sales.xlsx</span>');
    expect(html).not.toContain('ผ่านไป');
    expect(html).not.toContain('<img');
  });

  it('keeps thinking status in aria-label when stage is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AgentThinkingIndicator, { isEn: true }),
    );

    expect(html).toContain('aria-label="MataQorLab is thinking…');
    expect(html).toContain('animate-bounce');
    expect(html).not.toContain('animate-spin');
    expect(html).not.toContain('Analysis pipeline');
    expect(html).not.toContain('<ol');
  });

  it('prefers an explicit label override for accessibility', () => {
    const html = renderToStaticMarkup(
      React.createElement(AgentThinkingIndicator, {
        isEn: false,
        stage: 'intent',
        label: 'กำลังเตรียมข้อมูล…',
      }),
    );

    expect(html).toContain('aria-label="กำลังเตรียมข้อมูล…"');
    expect(html).not.toContain('วิเคราะห์เจตนา');
  });
});
