import { describe, expect, it, vi } from 'vitest';
import {
  captureDashboardPng,
  dashboardCaptureOptions,
} from './dashboardExport.js';

describe('dashboard export', () => {
  it('skips font stylesheet traversal that browsers block across origins', async () => {
    const renderer = vi.fn().mockResolvedValue('data:image/png;base64,ok');
    const node = {};

    await expect(captureDashboardPng(node, renderer)).resolves.toContain('image/png');
    expect(renderer).toHaveBeenCalledWith(node, expect.objectContaining({
      skipFonts: true,
      cacheBust: true,
      pixelRatio: 2,
    }));
    expect(dashboardCaptureOptions).toBe(Object.freeze(dashboardCaptureOptions));
  });

  it('rejects a missing dashboard target before invoking the renderer', () => {
    const renderer = vi.fn();

    expect(() => captureDashboardPng(null, renderer)).toThrow(/target/i);
    expect(renderer).not.toHaveBeenCalled();
  });
});
