// @ts-nocheck
const STYLES = {
  error: 'text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-900/40',
  success: 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900/40',
  info: 'text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-900/40 border-slate-200 dark:border-slate-700',
};

export default function AppBanner({ type = 'error', message, className = '' }) {
  if (!message) return null;

  return (
    <div
      role="alert"
      className={`mb-4 text-sm border p-3 rounded-lg ${STYLES[type] ?? STYLES.error} ${className}`}
    >
      {message}
    </div>
  );
}
