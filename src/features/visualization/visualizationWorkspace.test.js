import { describe, expect, it } from 'vitest';
import {
  clampVisualizationChatWidth,
  visualizationChatWidthFromKey,
  visualizationChatWidthFromPointer,
} from './visualizationWorkspace.js';

describe('Visualization split workspace', () => {
  it('keeps the Chat panel within the desktop bounds', () => {
    expect(clampVisualizationChatWidth(200)).toBe(360);
    expect(clampVisualizationChatWidth(450)).toBe(450);
    expect(clampVisualizationChatWidth(900)).toBe(520);
  });

  it('supports pointer and keyboard resizing', () => {
    expect(visualizationChatWidthFromPointer(1440, 1000)).toBe(440);
    expect(visualizationChatWidthFromKey(420, 'ArrowLeft')).toBe(444);
    expect(visualizationChatWidthFromKey(420, 'ArrowRight')).toBe(396);
  });
});
