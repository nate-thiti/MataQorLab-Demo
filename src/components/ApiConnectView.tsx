// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Globe, ShieldAlert, CheckCircle, RefreshCw, Plus, Trash2, Lock, Edit2, Shield, Save } from '@/components/icons';
import { t } from '../utils/i18n.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { localePath } from '../utils/locale.js';
import api from '../utils/api.js';
import RestApiConnectionFields from './RestApiConnectionFields';
import { DeleteConfirmationModal } from './ChatModals';
import {
  buildApiTestPayload,
  buildApiConnectionRecord,
  buildApiConnectionUpdate,
  EMPTY_HEADER,
  validateApiForm,
  headersFromConnection,
  formatRequestBodyForForm,
} from '../utils/apiConnectionConfig.js';

const defaultNewHeaders = () => [{ ...EMPTY_HEADER }];

const ApiConnectView = ({ isEn, user, m, plan, isPlanLoading = false, onSyncSuccess }) => {
  const router = useRouter();
  const routing = useLocaleRouting();
  const fileManagerCache = useFileManagerCache();
  const [connections, setConnections] = useState<any[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [name, setName] = useState('');
  const [method, setMethod] = useState('GET');
  const [url, setUrl] = useState('');
  const [headers, setHeaders] = useState(defaultNewHeaders);
  const [requestBodyText, setRequestBodyText] = useState('');
  const [editHeaders, setEditHeaders] = useState<any[]>([]);
  const [editRequestBodyText, setEditRequestBodyText] = useState('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testStatus, setTestStatus] = useState<any>(null);
  const [testErrorMessage, setTestErrorMessage] = useState('');
  const [saveStatus, setSaveStatus] = useState<any>(null);
  const [saveErrorMessage, setSaveErrorMessage] = useState('');
  const [testPassed, setTestPassed] = useState(false);
  
  const [syncingId, setSyncingId] = useState<any>(null);
  const [syncSuccess, setSyncSuccess] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [syncConfirmModal, setSyncConfirmModal] = useState({ show: false, connId: null });

  const [editingConn, setEditingConn] = useState<any>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<any>(null);
  const [editTesting, setEditTesting] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editTestStatus, setEditTestStatus] = useState<any>(null);
  const [editTestErrorMessage, setEditTestErrorMessage] = useState('');
  const [editSaveStatus, setEditSaveStatus] = useState<any>(null);
  const [editSaveErrorMessage, setEditSaveErrorMessage] = useState('');
  const [editTestPassed, setEditTestPassed] = useState(false);
  const [isMethodOpen, setIsMethodOpen] = useState(false);
  const [isEditMethodOpen, setIsEditMethodOpen] = useState(false);
  const [healthStatus, setHealthStatus] = useState<Record<string, any>>({}); // connId -> 'checking' | 'ok' | 'error'

  const userId = user?.id;
  const isLocked = !isPlanLoading && (plan?.name === 'Free' || !plan?.name);
  const connToDelete = connections.find(c => c.id === deleteConfirmId);

  const applyConnections = useCallback((rows, nextHealthStatus = {}) => {
    const nextRows = rows || [];
    const nextHealth = nextHealthStatus || {};
    setConnections(nextRows);
    if (userId) {
      fileManagerCache.setApiConnections(userId, { connections: nextRows, healthStatus: nextHealth });
    }
  }, [fileManagerCache, userId]);

  const testApiConnection = async ({ id, method, url, headers, requestBodyText }) => {
    await api.post('/api/v1/api-connections/test', {
      ...buildApiTestPayload({
      method,
      url,
      headers,
      requestBodyText,
      }),
      connection_id: id || null,
    });
  };

  const checkConnectionsHealth = useCallback(async (conns) => {
    if (!conns?.length) {
      setHealthStatus({});
      return;
    }

    const initial = Object.fromEntries(conns.map((c) => [c.id, 'checking']));
    setHealthStatus(initial);

    const results = {};
    await Promise.all(
      conns.map(async (conn) => {
        try {
          await testApiConnection({
            id: conn.id,
            method: conn.method,
            url: conn.url,
            headers: headersFromConnection(conn),
            requestBodyText: formatRequestBodyForForm(conn.request_body),
          });
          results[conn.id] = 'ok';
        } catch {
          results[conn.id] = 'error';
        }
      })
    );
    setHealthStatus(results);
    if (userId) {
      fileManagerCache.setApiConnections(userId, { connections: conns, healthStatus: results });
    }
  }, [fileManagerCache, userId]);

  const handleSync = async (connId, overwrite = false) => {
    if (!userId) return;
    setSyncingId(connId);
    setSyncError('');
    setSyncSuccess(false);
    
    try {
      const response = await api.post('/api/v1/api-connections/sync', {
        connection_id: connId,
        user_id: userId,
        overwrite: overwrite
      });
      
      if (response.data?.status === 'success') {
        setSyncSuccess(true);
        if (onSyncSuccess) {
          onSyncSuccess();
        }
        setTimeout(() => setSyncSuccess(false), 3000);
      } else {
        throw new Error(response.data?.message || 'Sync failed');
      }
    } catch (err: any) {
      console.error('Error syncing API:', err);
      const errMsg = err.response?.data?.detail || err.message || 'Failed to sync API data';
      setSyncError(errMsg);
    } finally {
      setSyncingId(null);
    }
  };


  const fetchConnections = useCallback(async () => {
    if (isPlanLoading) return;
    if (isLocked) return;
    if (!userId) return;
    try {
      const response = await api.get('/api/v1/connections');
      const rows = response.data?.api_connections || [];
      applyConnections(rows);
      checkConnectionsHealth(rows);
    } catch (err: any) {
      console.error('Error fetching API connections:', err);
    }
  }, [isPlanLoading, isLocked, userId, checkConnectionsHealth, applyConnections]);

  useEffect(() => {
    let cancelled = false;
    if (!userId) return undefined;

    const cached = fileManagerCache.getApiConnections(userId);
    if (cached) {
      const cachedConnections = cached.connections || [];
      const cachedHealth = cached.healthStatus || {};
      const hasHealthForAll = cachedConnections.every((conn) => cachedHealth[conn.id]);
      setConnections(cachedConnections);
      setHealthStatus(cachedHealth);
      if (cached.isFresh && hasHealthForAll) {
        return () => {
          cancelled = true;
        };
      }
      if (cached.isFresh) {
        checkConnectionsHealth(cachedConnections);
        return () => {
          cancelled = true;
        };
      }
    }

    if (isPlanLoading || isLocked) {
      return () => {
        cancelled = true;
      };
    }

    void (async () => {
      try {
        const response = await api.get('/api/v1/connections');
        if (cancelled) {
          return;
        }
        const rows = response.data?.api_connections || [];
        applyConnections(rows, {});
        checkConnectionsHealth(rows);
      } catch (err: any) {
        if (!cancelled) console.error('Error fetching API connections:', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId, isPlanLoading, isLocked, checkConnectionsHealth, applyConnections, fileManagerCache]);

  const headersSignature = JSON.stringify(headers);
  const editHeadersSignature = JSON.stringify(editHeaders);

  useEffect(() => {
    setTestPassed(false);
    setTestStatus(null);
  }, [name, method, url, headersSignature, requestBodyText]);

  useEffect(() => {
    if (!editingConn) return;
    setEditTestPassed(false);
    setEditTestStatus(null);
  }, [editingConn, editHeadersSignature, editRequestBodyText]);

  const buildAddApiPayload = () => ({
    method,
    url,
    headers,
    requestBodyText,
  });

  const resetAddForm = () => {
    setName('');
    setUrl('');
    setMethod('GET');
    setHeaders(defaultNewHeaders());
    setRequestBodyText('');
    setTestStatus(null);
    setTestErrorMessage('');
    setSaveStatus(null);
    setSaveErrorMessage('');
    setTestPassed(false);
  };

  const handleTestIntegration = async () => {
    const validation = validateApiForm({ name, url, method, requestBodyText });
    if (!validation.ok) {
      setTestStatus('error');
      setTestErrorMessage(
        t(
          m,
          validation.code === 'invalid_json_body'
            ? 'file_manager.api_invalid_json'
            : 'file_manager.api_required_fields'
        )
      );
      return;
    }

    setTesting(true);
    setTestStatus(null);
    setTestErrorMessage('');

    try {
      await testApiConnection(buildAddApiPayload());
      setTestStatus('success');
      setTestPassed(true);
    } catch (err: any) {
      setTestStatus('error');
      setTestPassed(false);
      const errMsg = err.response?.data?.detail || err.message || t(m, 'file_manager.api_fail');
      setTestErrorMessage(errMsg);
    } finally {
      setTesting(false);
    }
  };

  const handleSaveIntegration = async () => {
    if (!testPassed) {
      setSaveStatus('error');
      setSaveErrorMessage(t(m, 'file_manager.test_before_save'));
      return;
    }

    const validation = validateApiForm({ name, url, method, requestBodyText });
    if (!validation.ok) {
      setSaveStatus('error');
      setSaveErrorMessage(
        t(
          m,
          validation.code === 'invalid_json_body'
            ? 'file_manager.api_invalid_json'
            : 'file_manager.api_required_fields'
        )
      );
      return;
    }

    setSaving(true);
    setSaveStatus(null);
    setSaveErrorMessage('');

    try {
      await testApiConnection(buildAddApiPayload());

      await api.post('/api/v1/api-connections',
          buildApiConnectionRecord({
            user_id: userId,
            name,
            method,
            url,
            headers,
            requestBodyText,
          }));

      setSaveStatus('success');
      fetchConnections();

      setTimeout(() => {
        setIsAdding(false);
        resetAddForm();
      }, 1500);
    } catch (err: any) {
      setSaveStatus('error');
      const errMsg = err.response?.data?.detail || err.message || t(m, 'file_manager.api_fail');
      setSaveErrorMessage(errMsg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/v1/api-connections/${id}`);
      setConnections(prev => {
        const next = prev.filter(c => c.id !== id);
        const nextHealth = { ...healthStatus };
        delete nextHealth[id];
        setHealthStatus(nextHealth);
        if (userId) fileManagerCache.setApiConnections(userId, { connections: next, healthStatus: nextHealth });
        return next;
      });
    } catch (err: any) {
      console.error('Error deleting API connection:', err);
    }
  };

  const handleEditTestConnection = async () => {
    const validation = validateApiForm({
      name: editingConn.name,
      url: editingConn.url,
      method: editingConn.method,
      requestBodyText: editRequestBodyText,
    });
    if (!validation.ok) {
      setEditTestStatus('error');
      setEditTestErrorMessage(
        t(
          m,
          validation.code === 'invalid_json_body'
            ? 'file_manager.api_invalid_json'
            : 'file_manager.required_fields'
        )
      );
      return;
    }

    setEditTesting(true);
    setEditTestStatus(null);
    setEditTestErrorMessage('');

    try {
      await testApiConnection({
        id: editingConn.id,
        method: editingConn.method,
        url: editingConn.url,
        headers: editHeaders,
        requestBodyText: editRequestBodyText,
      });
      setEditTestStatus('success');
      setEditTestPassed(true);
    } catch (err: any) {
      setEditTestStatus('error');
      setEditTestPassed(false);
      const errMsg = err.response?.data?.detail || err.message || t(m, 'file_manager.api_fail');
      setEditTestErrorMessage(errMsg);
    } finally {
      setEditTesting(false);
    }
  };

  const handleUpdateApiConnection = async (e) => {
    e.preventDefault();
    if (!editTestPassed) {
      setEditSaveStatus('error');
      setEditSaveErrorMessage(t(m, 'file_manager.test_before_save'));
      return;
    }

    if (!editingConn.name || !editingConn.url) {
      setEditSaveStatus('error');
      setEditSaveErrorMessage(t(m, 'file_manager.required_fields'));
      return;
    }

    const validation = validateApiForm({
      name: editingConn.name,
      url: editingConn.url,
      method: editingConn.method,
      requestBodyText: editRequestBodyText,
    });
    if (!validation.ok) {
      setEditSaveStatus('error');
      setEditSaveErrorMessage(
        t(
          m,
          validation.code === 'invalid_json_body'
            ? 'file_manager.api_invalid_json'
            : 'file_manager.required_fields'
        )
      );
      return;
    }

    setEditSaving(true);
    setEditSaveStatus(null);
    setEditSaveErrorMessage('');

    try {
      await testApiConnection({
        method: editingConn.method,
        url: editingConn.url,
        headers: editHeaders,
        requestBodyText: editRequestBodyText,
      });

      await api.put(`/api/v1/api-connections/${editingConn.id}`,
          buildApiConnectionUpdate({
            name: editingConn.name,
            method: editingConn.method,
            url: editingConn.url,
            headers: editHeaders,
            requestBodyText: editRequestBodyText,
          })
        );

      setEditSaveStatus('success');
      fetchConnections();

      setTimeout(() => {
        setEditingConn(null);
        setEditTestStatus(null);
        setEditSaveStatus(null);
      }, 1000);
    } catch (err: any) {
      setEditSaveStatus('error');
      const errMsg = err.response?.data?.detail || err.message || t(m, 'file_manager.api_fail');
      setEditSaveErrorMessage(errMsg);
    } finally {
      setEditSaving(false);
    }
  };

  if (isPlanLoading && connections.length === 0) {
    return (
      <div className="app-module icon-motion-scope">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
            {t(m, 'file_manager.api_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.api_desc')}
          </p>
        </div>

        <div className="min-h-40" aria-hidden="true" />
      </div>
    );
  }

  if (isLocked) {
    return (
      <div className="app-module icon-motion-scope">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
            {t(m, 'file_manager.api_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.api_desc')}
          </p>
        </div>
        
        <div className="enterprise-panel p-12 md:p-16 text-center flex flex-col items-center max-w-3xl mx-auto">
          <div className="w-14 h-14 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-400 mb-6">
            <Lock className="w-7 h-7" />
          </div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-3">
            {t(m, 'file_manager.api_locked_title')}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed mb-8 max-w-md">
            {t(m, 'file_manager.api_locked_desc')}
          </p>
          <button
            onClick={() => router.push(localePath('/settings', routing))}
            className="px-6 py-3 btn-primary text-xs"
          >
            {t(m, 'file_manager.upgrade_plan_btn')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-module icon-motion-scope">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
            {t(m, 'file_manager.api_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.api_desc')}
          </p>
        </div>
        {!isAdding && (
          <button
            onClick={() => {
              resetAddForm();
              setIsAdding(true);
            }}
            className="flex items-center justify-center gap-2 px-4 py-2.5 btn-primary text-xs self-start sm:self-auto"
          >
            <Plus size={14} />
            {t(m, 'file_manager.add_conn')}
          </button>
        )}
      </div>

      <div className="trust-banner mb-6">
        <Shield size={14} className="text-slate-500 dark:text-slate-400 shrink-0" />
        <span>
          {isEn
            ? 'Connection credentials are encrypted at rest. API keys and database passwords are never exposed in logs.'
            : 'ข้อมูลการเชื่อมต่อถูกเข้ารหัสเมื่อจัดเก็บ รหัส API และรหัสผ่านฐานข้อมูลจะไม่ถูกเปิดเผยในระบบ'}
        </span>
      </div>

      {isAdding ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
          {/* Form */}
          <div className="lg:col-span-2 enterprise-panel p-8 space-y-6">
            <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
              
              {/* Connection Name */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1.5 px-1">{t(m, 'file_manager.conn_name')}</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t(m, 'file_manager.api_conn_name_placeholder')}
                  className="app-input w-full rounded-lg p-3 text-sm"
                  required
                />
              </div>

              {/* HTTP Method, URL, Headers, Body */}
              <RestApiConnectionFields
                isEn={isEn}
                m={m}
                method={method}
                setMethod={setMethod}
                url={url}
                setUrl={setUrl}
                headers={headers}
                setHeaders={setHeaders}
                requestBodyText={requestBodyText}
                setRequestBodyText={setRequestBodyText}
                isMethodOpen={isMethodOpen}
                setIsMethodOpen={setIsMethodOpen}
              />

              <div className="flex flex-col sm:flex-row gap-4 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsAdding(false);
                    resetAddForm();
                  }}
                  className="py-3.5 px-4 btn-secondary text-xs sm:flex-1"
                >
                  {t(m, 'chat.cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleTestIntegration}
                  disabled={testing || saving}
                  className="py-3.5 px-4 btn-secondary text-xs flex items-center justify-center gap-2 disabled:opacity-50 sm:flex-1"
                >
                  {testing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      {t(m, 'file_manager.testing_api')}
                    </>
                  ) : (
                    <>
                      <Globe className="w-4 h-4" />
                      {t(m, 'file_manager.test_api')}
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={handleSaveIntegration}
                  disabled={testing || saving || !testPassed}
                  title={!testPassed ? t(m, 'file_manager.test_before_save') : undefined}
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
              {!testPassed && (
                <p className="text-[10px] text-slate-450 dark:text-slate-500 text-center sm:text-right">
                  {t(m, 'file_manager.test_before_save_hint')}
                </p>
              )}
            </form>
          </div>

          {/* API Info & Status */}
          <div className="space-y-6">
            {testStatus === 'success' && (
              <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-6 rounded-xl flex flex-col items-center text-center">
                <CheckCircle className="w-12 h-12 text-green-500 mb-3" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_test_ok')}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-sans leading-relaxed">
                  {t(m, 'file_manager.api_test_ok_desc')}
                </p>
              </div>
            )}

            {testStatus === 'error' && (
              <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-6 rounded-xl flex flex-col items-center text-center">
                <ShieldAlert className="w-12 h-12 text-red-500 mb-3" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_fail')}
                </h3>
                <p className="text-xs text-red-655 dark:text-red-400 font-sans leading-relaxed">
                  {testErrorMessage}
                </p>
              </div>
            )}

            {saveStatus === 'success' && (
              <div className="bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-6 rounded-xl flex flex-col items-center text-center">
                <CheckCircle className="w-12 h-12 text-green-500 mb-3" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_success')}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-sans leading-relaxed">
                  {t(m, 'file_manager.api_success_desc')}
                </p>
              </div>
            )}

            {saveStatus === 'error' && (
              <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-6 rounded-xl flex flex-col items-center text-center">
                <ShieldAlert className="w-12 h-12 text-red-500 mb-3" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_fail')}
                </h3>
                <p className="text-xs text-red-655 dark:text-red-400 font-sans leading-relaxed">
                  {saveErrorMessage}
                </p>
              </div>
            )}

            <div className="enterprise-panel p-6">
              <h3 className="text-xs font-medium text-slate-600 dark:text-slate-400 uppercase tracking-wider mb-3">
                {t(m, 'file_manager.api_multi_title')}
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed font-sans">
                {t(m, 'file_manager.api_multi_desc')}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {syncSuccess && (
            <div className="p-4 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 text-green-700 dark:text-green-400 text-xs font-medium rounded-lg flex items-center gap-2">
              <CheckCircle className="w-4 h-4" />
              <span>{isEn ? 'Data synchronized successfully! Check your Files list.' : 'ดึงข้อมูลสำเร็จ! กรุณาตรวจสอบที่รายการไฟล์ของคุณ'}</span>
            </div>
          )}
          
          {syncError && (
            <div className="p-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-400 text-xs font-medium rounded-lg flex items-center gap-2">
              <ShieldAlert className="w-4 h-4" />
              <span>{syncError}</span>
            </div>
          )}

          <div className="enterprise-panel overflow-hidden">
            {connections.length > 0 ? (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {connections.map((conn) => (
                  <div key={conn.id} className="p-6 flex items-center justify-between transition-[background-color,box-shadow] hover:bg-slate-500/[0.08] hover:shadow-[inset_0_0_0_1px_rgba(148,163,184,0.16)]">
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-400 flex-shrink-0">
                        <Globe className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate">{conn.name}</h4>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate flex items-center gap-1.5 font-sans mt-0.5">
                          <span className="font-bold text-[10px] bg-slate-100 dark:bg-slate-900/60 px-1.5 py-0.5 rounded text-slate-650 dark:text-slate-300 uppercase">{conn.method}</span>
                          {conn.url}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 flex-shrink-0 ml-4">
                      <div className="hidden sm:block text-right font-sans">
                        {(() => {
                          const health = healthStatus[conn.id] || 'checking';
                          if (health === 'ok') {
                            return (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-900/40 px-2 py-0.5 rounded-md uppercase tracking-wider">
                                {t(m, 'file_manager.active')}
                              </span>
                            );
                          }
                          if (health === 'error') {
                            return (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/40 px-2 py-0.5 rounded-md uppercase tracking-wider">
                                {t(m, 'file_manager.inactive')}
                              </span>
                            );
                          }
                          return (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 px-2 py-0.5 rounded-md uppercase tracking-wider">
                              <RefreshCw className="w-3 h-3 animate-spin" />
                              {t(m, 'file_manager.checking')}
                            </span>
                          );
                        })()}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setSyncConfirmModal({ show: true, connId: conn.id })}
                          disabled={syncingId !== null}
                          className={`p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors ${
                            syncingId === conn.id ? 'text-[#d97706]' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                          }`}
                          title={isEn ? 'Sync Data' : 'ดึงข้อมูล'}
                        >
                          <RefreshCw className={`w-4 h-4 ${syncingId === conn.id ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={() => {
                            setEditingConn({ ...conn });
                            setEditHeaders(headersFromConnection(conn));
                            setEditRequestBodyText(formatRequestBodyForForm(conn.request_body));
                            setEditTestPassed(false);
                            setEditTestStatus(null);
                            setEditSaveStatus(null);
                            setEditTestErrorMessage('');
                            setEditSaveErrorMessage('');
                          }}
                          disabled={syncingId !== null}
                          className="p-2 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
                          title={isEn ? 'Edit Connection' : 'แก้ไขการเชื่อมต่อ'}
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setDeleteConfirmId(conn.id)}
                          disabled={syncingId !== null}
                          className="p-2 text-slate-400 hover:text-red-500 dark:hover:text-red-400 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
                          title={t(m, 'file_manager.delete_conn')}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-20 text-center px-6">
                <Globe className="w-14 h-14 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                <h4 className="text-base font-bold text-slate-900 dark:text-slate-200 mb-2">
                  {t(m, 'file_manager.no_api')}
                </h4>
                <p className="text-sm text-slate-500 dark:text-slate-455 mb-8 max-w-lg mx-auto font-sans leading-relaxed">
                  {t(m, 'file_manager.no_api_desc')}
                </p>
                <button
                  onClick={() => {
                    resetAddForm();
                    setIsAdding(true);
                  }}
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 btn-primary text-xs"
                >
                  <Plus size={14} />
                  {t(m, 'file_manager.add_conn')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal ตัวเลือกการบันทึกเมื่อดึงข้อมูล */}
      {syncConfirmModal.show && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="app-modal w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">
              {isEn ? 'Sync Options' : 'ตัวเลือกการดึงข้อมูล'}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-6 leading-relaxed font-sans">
              {isEn 
                ? 'Please select how you want to save the synchronized data in your storage.'
                : 'กรุณาเลือกวิธีการบันทึกข้อมูลที่ดึงมาจาก API ลงในพื้นที่จัดเก็บข้อมูลของคุณ'}
            </p>
            
            <div className="space-y-3 mb-6">
              <button
                onClick={() => {
                  const connId = syncConfirmModal.connId;
                  setSyncConfirmModal({ show: false, connId: null });
                  handleSync(connId, true); // overwrite
                }}
                className="w-full text-left p-4 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex flex-col gap-1"
              >
                <span className="text-xs font-medium text-slate-800 dark:text-slate-200">
                  {isEn ? 'Overwrite existing file' : 'บันทึกทับไฟล์เดิม'}
                </span>
                <span className="text-[10px] text-slate-450 dark:text-slate-500 leading-normal font-sans">
                  {isEn 
                    ? 'Updates a single file (e.g. api_name.json). Keeps your storage clean.' 
                    : 'อัปเดตไฟล์เดิมที่มีอยู่แล้ว (เช่น api_name.json) ช่วยประหยัดพื้นที่จัดเก็บข้อมูล'}
                </span>
              </button>

              <button
                onClick={() => {
                  const connId = syncConfirmModal.connId;
                  setSyncConfirmModal({ show: false, connId: null });
                  handleSync(connId, false); // create new (timestamped)
                }}
                className="w-full text-left p-4 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex flex-col gap-1"
              >
                <span className="text-xs font-medium text-slate-800 dark:text-slate-200">
                  {isEn ? 'Create a new file (with history)' : 'สร้างเป็นไฟล์ใหม่'}
                </span>
                <span className="text-[10px] text-slate-450 dark:text-slate-500 leading-normal font-sans">
                  {isEn 
                    ? 'Creates a new versioned file (e.g. 1718912_api_name.json) to keep history.' 
                    : 'สร้างไฟล์เวอร์ชันใหม่แยกต่างหาก (เช่น 1718912_api_name.json) เพื่อเก็บข้อมูลประวัติย้อนหลัง'}
                </span>
              </button>
            </div>

            <div className="flex justify-end gap-3 font-sans">
              <button
                onClick={() => setSyncConfirmModal({ show: false, connId: null })}
                className="inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {t(m, 'chat.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Edit API Connection Modal */}
      {editingConn && (
        <div className="fixed inset-0 z-[160] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm font-sans">
          <div className="app-modal w-full max-w-xl p-6 md:p-8 flex flex-col relative overflow-y-auto max-h-[90vh] no-scrollbar">
            <div className="flex items-center justify-between mb-6 w-full">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-base">
                {isEn ? 'Edit API Connection' : 'แก้ไขการเชื่อมต่อ REST API'}
              </h4>
              <button 
                onClick={() => {
                  setEditingConn(null);
                  setEditTestStatus(null);
                  setEditSaveStatus(null);
                }}
                className="p-2 rounded-lg transition-colors text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                title={t(m, 'chat.cancel')}
              >
                ✕
              </button>
            </div>

            {editTestStatus === 'success' && (
              <div className="mb-4 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-4 rounded-lg flex flex-col items-center text-center">
                <CheckCircle className="w-8 h-8 text-green-500 mb-2" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_test_ok')}
                </h3>
              </div>
            )}

            {editTestStatus === 'error' && (
              <div className="mb-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-4 rounded-lg flex flex-col items-center text-center">
                <ShieldAlert className="w-8 h-8 text-red-500 mb-2" />
                <p className="text-[10px] text-red-655 dark:text-red-400 font-sans leading-relaxed">
                  {editTestErrorMessage}
                </p>
              </div>
            )}

            {editSaveStatus === 'success' && (
              <div className="mb-4 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 p-4 rounded-lg flex flex-col items-center text-center">
                <CheckCircle className="w-8 h-8 text-green-500 mb-2" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.save_success')}
                </h3>
              </div>
            )}

            {editSaveStatus === 'error' && (
              <div className="mb-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-4 rounded-lg flex flex-col items-center text-center">
                <ShieldAlert className="w-8 h-8 text-red-500 mb-2" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white mb-1">
                  {t(m, 'file_manager.api_fail')}
                </h3>
                <p className="text-[10px] text-red-655 dark:text-red-400 font-sans leading-relaxed">
                  {editSaveErrorMessage}
                </p>
              </div>
            )}

            <form onSubmit={handleUpdateApiConnection} className="space-y-4">
              {/* Connection Name */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1.5 px-1">{t(m, 'file_manager.conn_name')}</label>
                <input
                  type="text"
                  value={editingConn.name}
                  onChange={(e) => setEditingConn({ ...editingConn, name: e.target.value })}
                  placeholder={t(m, 'file_manager.api_conn_name_placeholder')}
                  className="app-input w-full rounded-lg p-3 text-xs font-sans"
                  required
                />
              </div>

              {/* Method, URL, Headers, Body */}
              <RestApiConnectionFields
                isEn={isEn}
                m={m}
                method={editingConn.method}
                setMethod={(value) => setEditingConn({ ...editingConn, method: value })}
                url={editingConn.url}
                setUrl={(value) => setEditingConn({ ...editingConn, url: value })}
                headers={editHeaders}
                setHeaders={setEditHeaders}
                requestBodyText={editRequestBodyText}
                setRequestBodyText={setEditRequestBodyText}
                isMethodOpen={isEditMethodOpen}
                setIsMethodOpen={setIsEditMethodOpen}
                compact
              />

              <div className="flex flex-col sm:flex-row justify-end gap-3 pt-4 font-sans">
                <button
                  type="button"
                  onClick={() => {
                    setEditingConn(null);
                    setEditTestStatus(null);
                    setEditSaveStatus(null);
                  }}
                  className="px-5 py-2.5 btn-secondary text-xs"
                >
                  {t(m, 'chat.cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleEditTestConnection}
                  disabled={editTesting || editSaving}
                  className="px-5 py-2.5 btn-secondary text-xs flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {editTesting ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      {t(m, 'file_manager.testing_api')}
                    </>
                  ) : (
                    t(m, 'file_manager.test_api')
                  )}
                </button>
                <button
                  type="submit"
                  disabled={editTesting || editSaving || !editTestPassed}
                  title={!editTestPassed ? t(m, 'file_manager.test_before_save') : undefined}
                  className="px-6 py-2.5 btn-primary text-xs flex items-center gap-2 disabled:opacity-50"
                >
                  {editSaving ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      {t(m, 'file_manager.saving_connection')}
                    </>
                  ) : (
                    t(m, 'file_manager.save_connection')
                  )}
                </button>
              </div>
              {!editTestPassed && (
                <p className="text-[10px] text-slate-450 dark:text-slate-500 text-right pt-1">
                  {t(m, 'file_manager.test_before_save_hint')}
                </p>
              )}
            </form>
          </div>
        </div>
      )}
      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        isOpen={Boolean(deleteConfirmId)}
        onClose={() => setDeleteConfirmId(null)}
        onConfirm={() => {
          handleDelete(deleteConfirmId);
          setDeleteConfirmId(null);
        }}
        title={isEn ? 'Delete this connection?' : 'ลบการเชื่อมต่อนี้หรือไม่?'}
        subject={connToDelete?.name}
        message={
          isEn
            ? 'This API connection will be permanently removed and cannot be recovered.'
            : 'การเชื่อมต่อ API นี้จะถูกลบอย่างถาวร และกู้คืนไม่ได้'
        }
        confirmButtonText={isEn ? 'Delete connection' : 'ลบการเชื่อมต่อ'}
        cancelButtonText={t(m, 'chat.cancel')}
      />
    </div>
  );
};

export default ApiConnectView;
