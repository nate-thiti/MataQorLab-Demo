// @ts-nocheck
import { t } from '../utils/i18n.js';
import { getDatabaseProvider } from '../utils/databaseProviders.js';

const inputClass =
  'app-input w-full p-3 text-sm';

const labelClass = 'app-field-label';

const DbConnectionFormFields = ({
  isEn,
  m,
  provider,
  name,
  setName,
  host,
  setHost,
  port,
  setPort,
  dbName,
  setDbName,
  username,
  setUsername,
  password,
  setPassword,
  compact = false,
  namePlaceholder,
}) => {
  const meta = getDatabaseProvider(provider);
  const hostLabel = isEn
    ? meta.hostLabelEn || t(m, 'file_manager.host')
    : meta.hostLabelTh || t(m, 'file_manager.host');
  const dbLabel = isEn
    ? meta.dbLabelEn || t(m, 'file_manager.db_name')
    : meta.dbLabelTh || t(m, 'file_manager.db_name');

  return (
    <div className={compact ? 'space-y-4' : 'space-y-6'}>
      <div>
        <label className={labelClass}>{t(m, 'file_manager.conn_name')}</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={namePlaceholder || t(m, 'file_manager.sql_conn_name_placeholder')}
          className={`${inputClass} ${compact ? 'text-xs' : ''}`}
          required
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <label className={labelClass}>{hostLabel}</label>
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder={meta.hostPlaceholder}
            className={`${inputClass} ${compact ? 'text-xs' : ''}`}
            required
          />
        </div>
        <div>
          <label className={labelClass}>{t(m, 'file_manager.port')}</label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(e.target.value)}
            className={`${inputClass} ${compact ? 'text-xs' : ''}`}
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>{dbLabel}</label>
          <input
            type="text"
            value={dbName}
            onChange={(e) => setDbName(e.target.value)}
            placeholder={meta.dbPlaceholder}
            className={`${inputClass} ${compact ? 'text-xs' : ''}`}
            required
          />
        </div>
        <div>
          <label className={labelClass}>{t(m, 'file_manager.username')}</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="db_user"
            className={`${inputClass} ${compact ? 'text-xs' : ''}`}
            required
          />
        </div>
      </div>

      <div>
        <label className={labelClass}>{t(m, 'file_manager.password')}</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••••••"
          className={`${inputClass} ${compact ? 'text-xs' : ''}`}
        />
        <p className="text-[10px] text-slate-450 dark:text-slate-500 mt-2 px-1 font-sans leading-relaxed">
          {t(m, 'file_manager.db_provider_hint')}
        </p>
      </div>
    </div>
  );
};

export default DbConnectionFormFields;
