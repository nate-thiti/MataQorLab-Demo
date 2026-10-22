// @ts-nocheck
import { ArrowLeft, Database, RefreshCw, Save } from '@/components/icons';
import { t } from '../utils/i18n.js';
import {
  DB_PROVIDER_CATEGORIES,
  getProviderLabel,
  providersByCategory,
} from '../utils/databaseProviders.js';
import DbProviderLogo from './DbProviderLogo';
import DbConnectionFormFields from './DbConnectionFormFields';

const DbAddConnectionModal = ({
  isEn,
  m,
  step,
  provider,
  onSelectProvider,
  onBackToGrid,
  onClose,
  onTest,
  onSave,
  testing,
  saving,
  canSave,
  testStatus,
  testErrorMessage,
  saveStatus,
  saveErrorMessage,
  form,
}) => {
  const {
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
  } = form;

  const busy = testing || saving;

  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm font-sans">
      <div className="app-modal w-full max-w-3xl flex flex-col max-h-[92vh] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {step === 'form' && (
              <button
                type="button"
                onClick={onBackToGrid}
                className="p-2 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                title={t(m, 'file_manager.db_back_to_grid')}
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 dark:text-white truncate">
                {step === 'pick'
                  ? t(m, 'file_manager.db_pick_provider')
                  : t(m, 'file_manager.db_configure_provider')}
              </h3>
              {step === 'form' && (
                <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                  {getProviderLabel(provider)}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            ✕
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6">
          {step === 'pick' ? (
            <div className="space-y-8">
              {DB_PROVIDER_CATEGORIES.map((cat) => (
                <div key={cat.id}>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-450 dark:text-slate-500 mb-3 px-1">
                    {isEn ? cat.labelEn : cat.labelTh}
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                    {providersByCategory(cat.id).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => onSelectProvider(item.id)}
                        className="group p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-[#d97706] dark:hover:border-amber-600 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-all flex flex-col items-center gap-3 text-center focus:outline-none focus:ring-2 focus:ring-[#d97706]/40"
                      >
                        <DbProviderLogo providerId={item.id} className="w-12 h-12" />
                        <span className="text-xs font-medium text-slate-800 dark:text-slate-100 leading-tight">
                          {item.label}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex items-center gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800">
                <DbProviderLogo providerId={provider} className="w-14 h-14" />
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                    {getProviderLabel(provider)}
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    {t(m, 'file_manager.db_readonly_hint')}
                  </p>
                </div>
              </div>

              {testStatus === 'success' && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-4 rounded-lg text-center">
                  <p className="text-xs font-bold text-green-700 dark:text-green-400">
                    {t(m, 'file_manager.sql_test_ok')}
                  </p>
                  <p className="text-[10px] text-green-650 dark:text-green-400/80 mt-1">
                    {t(m, 'file_manager.sql_test_ok_desc')}
                  </p>
                </div>
              )}

              {testStatus === 'error' && (
                <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-4 rounded-lg text-center">
                  <p className="text-xs text-red-700 dark:text-red-400">{testErrorMessage}</p>
                </div>
              )}

              {saveStatus === 'success' && (
                <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-4 rounded-lg text-center">
                  <p className="text-xs font-bold text-green-700 dark:text-green-400">
                    {t(m, 'file_manager.sql_success')}
                  </p>
                  <p className="text-[10px] text-green-650 dark:text-green-400/80 mt-1">
                    {t(m, 'file_manager.sql_success_desc')}
                  </p>
                </div>
              )}

              {saveStatus === 'error' && (
                <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-4 rounded-lg text-center">
                  <p className="text-xs text-red-700 dark:text-red-400">{saveErrorMessage}</p>
                </div>
              )}

              <div className="space-y-6">
                <DbConnectionFormFields
                  isEn={isEn}
                  m={m}
                  provider={provider}
                  name={name}
                  setName={setName}
                  host={host}
                  setHost={setHost}
                  port={port}
                  setPort={setPort}
                  dbName={dbName}
                  setDbName={setDbName}
                  username={username}
                  setUsername={setUsername}
                  password={password}
                  setPassword={setPassword}
                />

                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                  <button type="button" onClick={onClose} className="py-3.5 px-4 btn-secondary text-xs sm:flex-1">
                    {t(m, 'chat.cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={onTest}
                    disabled={busy}
                    className="py-3.5 px-4 btn-secondary text-xs flex items-center justify-center gap-2 disabled:opacity-50 sm:flex-1"
                  >
                    {testing ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        {t(m, 'file_manager.testing_sql')}
                      </>
                    ) : (
                      <>
                        <Database className="w-4 h-4" />
                        {t(m, 'file_manager.test_sql')}
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={onSave}
                    disabled={busy || !canSave}
                    title={!canSave ? t(m, 'file_manager.test_before_save') : undefined}
                    className="py-3.5 px-4 btn-primary text-xs flex items-center justify-center gap-2 disabled:opacity-50 sm:flex-[1.2]"
                  >
                    {saving ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        {t(m, 'file_manager.saving_connection')}
                      </>
                    ) : (
                      <>
                        <Save className="w-4 h-4" />
                        {t(m, 'file_manager.save_connection')}
                      </>
                    )}
                  </button>
                </div>
                {!canSave && (
                  <p className="text-[10px] text-slate-450 dark:text-slate-500 text-center sm:text-right">
                    {t(m, 'file_manager.test_before_save_hint')}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DbAddConnectionModal;
