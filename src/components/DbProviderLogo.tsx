// @ts-nocheck
import { useState } from 'react';
import { getProviderLabel } from '../utils/databaseProviders.js';
import { dbProviderLogoSrc } from '../utils/dbProviderLogoFiles.js';

export { dbProviderLogoSrc } from '../utils/dbProviderLogoFiles.js';

/** Brand-colored fallback when SVG is missing or fails to load. */
const FALLBACK_STYLES = {
  postgres: { bg: '#336791', text: 'PG' },
  mysql: { bg: '#00758F', text: 'My' },
  mariadb: { bg: '#003545', text: 'Ma' },
  mssql: { bg: '#CC2927', text: 'MS' },
  oracle: { bg: '#F80000', text: 'Or' },
  db2: { bg: '#052FAD', text: 'Db' },
  snowflake: { bg: '#29B5E8', text: '❄' },
  bigquery: { bg: '#4285F4', text: 'BQ' },
  redshift: { bg: '#232F3E', text: 'RS' },
  databricks: { bg: '#FF3621', text: 'Db' },
  clickhouse: { bg: '#FCFF00', text: 'CH', fg: '#111827' },
};

const DbProviderLogo = ({ providerId, className = 'w-10 h-10', compact = false }) => {
  const [useFallback, setUseFallback] = useState(false);
  const title = getProviderLabel(providerId);
  const src = dbProviderLogoSrc(providerId);

  if (!useFallback && src) {
    return (
      <img
        src={src}
        alt={title}
        title={title}
        className={`${className} rounded-xl object-contain bg-white dark:bg-slate-900 p-1.5 shadow-sm border border-slate-200/80 dark:border-slate-700 shrink-0`}
        onError={() => setUseFallback(true)}
      />
    );
  }

  const style = FALLBACK_STYLES[providerId] || FALLBACK_STYLES.postgres;
  const fg = style.fg || '#ffffff';

  return (
    <div
      className={`${className} rounded-xl flex items-center justify-center shadow-sm border border-black/5 shrink-0`}
      style={{ backgroundColor: style.bg, color: fg }}
      title={title}
      aria-hidden={compact ? undefined : true}
    >
      <span className={`font-bold ${compact ? 'text-[10px]' : 'text-sm'}`}>{style.text}</span>
    </div>
  );
};

export default DbProviderLogo;
