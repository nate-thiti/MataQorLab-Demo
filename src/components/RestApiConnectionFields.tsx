// @ts-nocheck
import { ChevronDown, Plus, Trash2 } from '@/components/icons';
import { t } from '../utils/i18n.js';
import { EMPTY_HEADER, POST_BODY_PLACEHOLDER } from '../utils/apiConnectionConfig.js';

const inputClass =
  'app-input w-full p-3 text-sm';

const labelClass = 'app-field-label';

const RestApiConnectionFields = ({
  isEn,
  m,
  method,
  setMethod,
  url,
  setUrl,
  headers,
  setHeaders,
  requestBodyText,
  setRequestBodyText,
  isMethodOpen,
  setIsMethodOpen,
  compact = false,
}) => {
  const showBody = (method || 'GET').toUpperCase() !== 'GET';

  const addHeader = () => setHeaders([...(headers || []), { ...EMPTY_HEADER }]);

  const updateHeader = (index, field, value) => {
    setHeaders(
      (headers || []).map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );
  };

  const removeHeader = (index) => {
    const next = (headers || []).filter((_, i) => i !== index);
    setHeaders(next.length ? next : [{ ...EMPTY_HEADER }]);
  };

  return (
    <div className={compact ? 'space-y-4' : 'space-y-6'}>
      <div className={`grid grid-cols-1 ${compact ? 'grid-cols-3 gap-4' : 'md:grid-cols-4 gap-4'}`}>
        <div>
          <label className={labelClass}>{t(m, 'file_manager.api_method')}</label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsMethodOpen(!isMethodOpen)}
              className={`${inputClass} flex justify-between items-center cursor-pointer ${compact ? 'text-xs p-3' : ''}`}
            >
              <span className="font-medium">{method}</span>
              <ChevronDown className={`w-4 h-4 text-[#d97706] transition-transform ${isMethodOpen ? 'rotate-180' : ''}`} strokeWidth={1.5} />
            </button>
            {isMethodOpen && (
              <>
                <div className="fixed inset-0 z-[100]" onClick={() => setIsMethodOpen(false)} />
                <div className="absolute left-0 right-0 mt-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-[110] py-1 overflow-hidden">
                  {['GET', 'POST', 'PUT', 'PATCH'].map((verb) => (
                    <button
                      key={verb}
                      type="button"
                      onClick={() => {
                        setMethod(verb);
                        setIsMethodOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/50 ${
                        method === verb
                          ? 'text-[#d97706] font-medium bg-slate-100 dark:bg-slate-700/30'
                          : 'text-slate-700 dark:text-slate-200'
                      }`}
                    >
                      {verb}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
        <div className={compact ? 'col-span-2' : 'md:col-span-3'}>
          <label className={labelClass}>{t(m, 'file_manager.api_endpoint_url')}</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t(m, 'file_manager.api_url_placeholder')}
            className={`${inputClass} ${compact ? 'text-xs' : ''}`}
            required
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-455 dark:text-slate-550">
            {t(m, 'file_manager.api_request_headers')}
          </h3>
          <button
            type="button"
            onClick={addHeader}
            className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-[#d97706] hover:opacity-80"
          >
            <Plus size={12} />
            {t(m, 'file_manager.api_add_header')}
          </button>
        </div>
        <div className="space-y-3">
          {(headers || [{ ...EMPTY_HEADER }]).map((row, index) => (
            <div key={`header-${index}`} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3">
              <div>
                <label className={labelClass}>{t(m, 'file_manager.api_header_key')}</label>
                <input
                  type="text"
                  value={row.key}
                  onChange={(e) => updateHeader(index, 'key', e.target.value)}
                  placeholder={t(m, 'file_manager.api_header_key_placeholder')}
                  className={`${inputClass} ${compact ? 'text-xs' : ''}`}
                />
              </div>
              <div>
                <label className={labelClass}>{t(m, 'file_manager.api_header_value')}</label>
                <input
                  type="text"
                  value={row.value}
                  onChange={(e) => updateHeader(index, 'value', e.target.value)}
                  placeholder="••••••••"
                  className={`${inputClass} ${compact ? 'text-xs' : ''}`}
                />
              </div>
              <div className="flex items-end">
                <button
                  type="button"
                  onClick={() => removeHeader(index)}
                  className="p-3 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-400 hover:text-red-500 hover:border-red-200 dark:hover:border-red-900/40 transition-colors"
                  title={t(m, 'file_manager.api_remove_header')}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-slate-450 dark:text-slate-500 mt-2 px-1 font-sans leading-relaxed">
          {t(m, 'file_manager.api_headers_hint')}
        </p>
      </div>

      {showBody && (
        <div>
          <label className={labelClass}>{t(m, 'file_manager.api_request_body')}</label>
          <textarea
            rows={compact ? 6 : 8}
            value={requestBodyText}
            onChange={(e) => setRequestBodyText(e.target.value)}
            placeholder={POST_BODY_PLACEHOLDER}
            className={`${inputClass} font-mono text-xs resize-y min-h-[120px]`}
          />
          <p className="text-[10px] text-slate-450 dark:text-slate-500 mt-2 px-1 font-sans leading-relaxed">
            {t(m, 'file_manager.api_body_hint')}
          </p>
          <p className="text-[10px] text-slate-450 dark:text-slate-500 mt-1 px-1 font-mono leading-relaxed break-all">
            {t(m, 'file_manager.api_pagination_hint')}
          </p>
        </div>
      )}
    </div>
  );
};

export default RestApiConnectionFields;
