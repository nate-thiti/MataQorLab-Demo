import { describe, expect, it } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import SuggestedQuestions, { shouldShowSuggestedQuestions } from './SuggestedQuestions';

describe('SuggestedQuestions', () => {
  it('renders at most three immediate-send actions', () => {
    const html = renderToStaticMarkup(
      React.createElement(SuggestedQuestions, {
        prompts: ['One', 'Two', 'Three', 'Four'],
        isEn: true,
        onSelect: () => {},
      }),
    );

    expect(html).toContain('Continue exploring');
    expect(html).toContain('One');
    expect(html).toContain('Three');
    expect(html).not.toContain('Four');
    expect((html.match(/<button/g) || [])).toHaveLength(3);
  });

  it('disables every action while the parent is generating', () => {
    const html = renderToStaticMarkup(
      React.createElement(SuggestedQuestions, {
        prompts: ['One', 'Two'],
        disabled: true,
        onSelect: () => {},
      }),
    );

    expect((html.match(/disabled=""/g) || [])).toHaveLength(2);
  });

  it('only allows suggestions on the latest completed assistant answer', () => {
    const base = {
      isLatestAssistant: true,
      failed: false,
      isGenerating: false,
      conversationalSetupActive: false,
      promptCount: 3,
      hasHandler: true,
    };

    expect(shouldShowSuggestedQuestions(base)).toBe(true);
    expect(shouldShowSuggestedQuestions({ ...base, isLatestAssistant: false })).toBe(false);
    expect(shouldShowSuggestedQuestions({ ...base, failed: true })).toBe(false);
    expect(shouldShowSuggestedQuestions({ ...base, isGenerating: true })).toBe(false);
    expect(shouldShowSuggestedQuestions({ ...base, conversationalSetupActive: true })).toBe(false);
  });
});
