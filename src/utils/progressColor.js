/** Returns CSS class for usage progress bars (semantic only). */
export const getProgressFillClass = (percentage) => {
  if (percentage >= 95) return 'progress-fill-danger';
  if (percentage >= 80) return 'progress-fill-warning';
  return 'progress-fill';
};
