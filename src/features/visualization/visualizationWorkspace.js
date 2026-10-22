export const VISUALIZATION_CHAT_MIN_WIDTH = 360;
export const VISUALIZATION_CHAT_MAX_WIDTH = 520;
export const VISUALIZATION_CHAT_DEFAULT_WIDTH = 420;

export function clampVisualizationChatWidth(value) {
  const width = Number(value);
  if (!Number.isFinite(width)) return VISUALIZATION_CHAT_DEFAULT_WIDTH;
  return Math.min(
    VISUALIZATION_CHAT_MAX_WIDTH,
    Math.max(VISUALIZATION_CHAT_MIN_WIDTH, Math.round(width)),
  );
}

export function visualizationChatWidthFromPointer(viewportWidth, pointerX) {
  return clampVisualizationChatWidth(Number(viewportWidth) - Number(pointerX));
}

export function visualizationChatWidthFromKey(width, key) {
  if (key === 'ArrowLeft') return clampVisualizationChatWidth(Number(width) + 24);
  if (key === 'ArrowRight') return clampVisualizationChatWidth(Number(width) - 24);
  return clampVisualizationChatWidth(width);
}
