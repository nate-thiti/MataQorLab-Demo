import { describe, expect, it } from 'vitest';
import { visualizationContextForRequest } from '../visualizationChatContext.js';

const context = {
  reportId: 'report-1',
  widgetId: 'ranking',
  filters: { branch: 'North' },
  sourceConfig: { type: 'file', file_name: 'sales.xlsx' },
};

describe('Visualization Chat context', () => {
  it('sends the active report, widget and filters for the report source', () => {
    expect(visualizationContextForRequest(context, { attachedFileName: 'sales.xlsx' }))
      .toEqual({
        report_id: 'report-1',
        widget_id: 'ranking',
        filters: { branch: 'North' },
      });
  });

  it('drops report context when the user explicitly selects another source', () => {
    expect(visualizationContextForRequest(context, { attachedFileName: 'inventory.xlsx' }))
      .toBeNull();
  });
});
