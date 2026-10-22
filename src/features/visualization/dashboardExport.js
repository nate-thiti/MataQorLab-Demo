import { toPng } from 'html-to-image';

export const dashboardCaptureOptions = Object.freeze({
  cacheBust: true,
  pixelRatio: 2,
  backgroundColor: '#f4f5f7',
  // html-to-image otherwise walks document.styleSheets and reads cssRules to
  // embed fonts. Browsers correctly reject that for cross-origin stylesheets.
  skipFonts: true,
});

export function captureDashboardPng(node, renderer = toPng) {
  if (!node) throw new Error('Dashboard export target was not found');
  return renderer(node, dashboardCaptureOptions);
}
