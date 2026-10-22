// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Database, ShieldAlert, CheckCircle, RefreshCw, Plus, Trash2, Lock, Edit2, Shield } from '@/components/icons';
import { t } from '../utils/i18n.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { localePath } from '../utils/locale.js';
import api from '../utils/api.js';
import DbAddConnectionModal from './DbAddConnectionModal';
import DbConnectionFormFields from './DbConnectionFormFields';
import DbProviderLogo from './DbProviderLogo';
import { DeleteConfirmationModal } from './ChatModals';
import {
  defaultPortForProvider,
  getProviderLabel,
} from '../utils/databaseProviders.js';

const emptyFormState = () => ({
  provider: 'postgres',
  name: '',
  host: '',
  port: '5432',
  dbName: '',
  username: '',
  password: '',
});

const DatabaseConnectView = ({ isEn, user, m, plan, isPlanLoading = false, onSyncSuccess }) => {
  const router = useRouter();
  const routing = useLocaleRouting();
  const fileManagerCache = useFileManagerCache();
  const [connections, setConnections] = useState<any[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addStep, setAddStep] = useState('pick'); // 'pick' | 'form'
  const [provider, setProvider] = useState('postgres');
  const [name, setName] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState('5432');
  const [dbName, setDbName] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testStatus, setTestStatus] = useState<any>(null); // 'success' | 'error' | null
  const [testErrorMessage, setTestErrorMessage] = useState('');
  const [saveStatus, setSaveStatus] = useState<any>(null);
  const [saveErrorMessage, setSaveErrorMessage] = useState('');
  const [testPassed, setTestPassed] = useState(false);
  
  const [syncingId, setSyncingId] = useState<any>(null);
  const [syncSuccess, setSyncSuccess] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [syncModal, setSyncModal] = useState({
    show: false,
    connId: null,
    queryType: 'table', // 'table' | 'query'
    target: '',
    format: 'csv', // 'csv' | 'json'
    overwrite: true
  });

  const [editingConn, setEditingConn] = useState<any>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<any>(null);
  const [editTesting, setEditTesting] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editTestStatus, setEditTestStatus] = useState<any>(null);
  const [editTestErrorMessage, setEditTestErrorMessage] = useState('');
  const [editSaveStatus, setEditSaveStatus] = useState<any>(null);
  const [editSaveErrorMessage, setEditSaveErrorMessage] = useState('');
  const [editTestPassed, setEditTestPassed] = useState(false);
  const [healthStatus, setHealthStatus] = useState<Record<string, any>>({}); // connId -> 'checking' | 'ok' | 'error'

  const userId = user?.id;
  const isLocked = !isPlanLoading && !['Pro', 'Enterprise'].includes(plan?.name);
  const connToDelete = connections.find(c => c.id === deleteConfirmId);

  const applyConnections = useCallback((rows, nextHealthStatus = {}) => {
    const nextRows = rows || [];
    const nextHealth = nextHealthStatus || {};
    setConnections(nextRows);
    if (userId) {
      fileManagerCache.setDatabaseConnections(userId, { connections: nextRows, healthStatus: nextHealth });
    }
  }, [fileManagerCache, userId]);

  const testDbConnection = async ({ id, provider, host, port, db_name, username, password_encrypted, password: rawPassword }) => {
    await api.post('/api/v1/db-connections/test', {
      connection_id: id || null,
      provider,
      host,
      port: parseInt(port, 10),
      db_name,
      username,
      password: rawPassword ?? password_encrypted ?? '',
    });
  };

  const validateDbForm = ({ name, host, db_name, username }) => {
    if (!name || !host || !db_name || !username) {
      return { ok: false, message: t(m, 'file_manager.required_fields') };
    }
    return { ok: true };
  };

  const buildAddFormPayload = () => ({
    provider,
    host,
    port,
    db_name: dbName,
    username,
    password_encrypted: password,
  });

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
          await testDbConnection(conn);
          results[conn.id] = 'ok';
        } catch {
          results[conn.id] = 'error';
        }
      })
    );
    setHealthStatus(results);
    if (userId) {
      fileManagerCache.setDatabaseConnections(userId, { connections: conns, healthStatus: results });
    }
  }, [fileManagerCache, userId]);

  const handleSyncDb = async () => {
    if (!userId || !syncModal.connId) return;
    const { connId, target, format, overwrite } = syncModal;
    
    if (!target.trim()) {
      setSyncError(isEn ? 'Please specify a table name or SQL query.' : 'กรุณาระบุชื่อตารางหรือคำสั่ง SQL Query');
      return;
    }
    
    setSyncingId(connId);
    setSyncError('');
    setSyncSuccess(false);
    setSyncModal(prev => ({ ...prev, show: false }));
    
    try {
      const response = await api.post('/api/v1/db-connections/sync', {
        connection_id: connId,
        user_id: userId,
        query_or_table: target,
        file_format: format,
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
      console.error('Error syncing SQL database:', err);
      const errMsg = err.response?.data?.detail || err.message || 'Failed to sync database data';
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
      const rows = response.data?.database_connections || [];
      applyConnections(rows);
      checkConnectionsHealth(rows);
    } catch (err: any) {
      console.error('Error fetching database connections:', err);
    }
  }, [isPlanLoading, isLocked, userId, checkConnectionsHealth, applyConnections]);

  useEffect(() => {
    let cancelled = false;
    if (!userId) return undefined;

    const cached = fileManagerCache.getDatabaseConnections(userId);
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
        const rows = response.data?.database_connections || [];
        applyConnections(rows, {});
        checkConnectionsHealth(rows);
      } catch (err: any) {
        if (!cancelled) console.error('Error fetching database connections:', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId, isPlanLoading, isLocked, checkConnectionsHealth, applyConnections, fileManagerCache]);

  useEffect(() => {
    setTestPassed(false);
    setTestStatus(null);
  }, [provider, name, host, port, dbName, username, password]);

  useEffect(() => {
    if (!editingConn) return;
    setEditTestPassed(false);
    setEditTestStatus(null);
  }, [editingConn]);

  const resetAddForm = () => {
    const initial = emptyFormState();
    setProvider(initial.provider);
    setName(initial.name);
    setHost(initial.host);
    setPort(initial.port);
    setDbName(initial.dbName);
    setUsername(initial.username);
    setPassword(initial.password);
    setAddStep('pick');
    setTestStatus(null);
    setTestErrorMessage('');
    setSaveStatus(null);
    setSaveErrorMessage('');
    setTestPassed(false);
  };

  const openAddModal = () => {
    resetAddForm();
    setShowAddModal(true);
  };

  const closeAddModal = () => {
    setShowAddModal(false);
    resetAddForm();
  };

  const selectProviderForAdd = (prov) => {
    setProvider(prov);
    setPort(defaultPortForProvider(prov));
    setAddStep('form');
    setTestStatus(null);
    setTestErrorMessage('');
    setSaveStatus(null);
    setSaveErrorMessage('');
  };

  const handleTestConnection = async () => {
    const validation = validateDbForm({ name, host, db_name: dbName, username });
    if (!validation.ok) {
      setTestStatus('error');
      setTestErrorMessage(validation.message);
      return;
    }

    setTesting(true);
    setTestStatus(null);
    setTestErrorMessage('');

    try {
      await testDbConnection(buildAddFormPayload());
      setTestStatus('success');
      setTestPassed(true);
    } catch (err: any) {
      setTestStatus('error');
      setTestPassed(false);
      const errMsg = err.response?.data?.detail || err.message || 'Failed to test database connection';
      setTestErrorMessage(errMsg);
    } finally {
      setTesting(false);
    }
  };

  const handleSaveConnection = async () => {
    if (!testPassed) {
      setSaveStatus('error');
      setSaveErrorMessage(t(m, 'file_manager.test_before_save'));
      return;
    }

    const validation = validateDbForm({ name, host, db_name: dbName, username });
    if (!validation.ok) {
      setSaveStatus('error');
      setSaveErrorMessage(validation.message);
      return;
    }

    setSaving(true);
    setSaveStatus(null);
    setSaveErrorMessage('');

    try {
      await testDbConnection(buildAddFormPayload());

      await api.post('/api/v1/db-connections', {
        provider, name, host, port: parseInt(port, 10), db_name: dbName,
        username, password,
      });

      setSaveStatus('success');
      fetchConnections();

      setTimeout(() => {
        closeAddModal();
      }, 1500);
    } catch (err: any) {
      setSaveStatus('error');
      const errMsg = err.response?.data?.detail || err.message || 'Failed to verify or save database connection';
      setSaveErrorMessage(errMsg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/v1/db-connections/${id}`);
      setConnections(prev => {
        const next = prev.filter(c => c.id !== id);
        const nextHealth = { ...healthStatus };
        delete nextHealth[id];
        setHealthStatus(nextHealth);
        if (userId) fileManagerCache.setDatabaseConnections(userId, { connections: next, healthStatus: nextHealth });
        return next;
      });
    } catch (err: any) {
      console.error('Error deleting connection:', err);
    }
  };

  const handleEditTestConnection = async () => {
    const validation = validateDbForm(editingConn);
    if (!validation.ok) {
      setEditTestStatus('error');
      setEditTestErrorMessage(validation.message);
      return;
    }

    setEditTesting(true);
    setEditTestStatus(null);
    setEditTestErrorMessage('');

    try {
      await testDbConnection(editingConn);
      setEditTestStatus('success');
      setEditTestPassed(true);
    } catch (err: any) {
      setEditTestStatus('error');
      setEditTestPassed(false);
      const errMsg = err.response?.data?.detail || err.message || 'Failed to test database connection';
      setEditTestErrorMessage(errMsg);
    } finally {
      setEditTesting(false);
    }
  };

  const handleUpdateConnection = async (e) => {
    e.preventDefault();
    if (!editTestPassed) {
      setEditSaveStatus('error');
      setEditSaveErrorMessage(t(m, 'file_manager.test_before_save'));
      return;
    }

    const validation = validateDbForm(editingConn);
    if (!validation.ok) {
      setEditSaveStatus('error');
      setEditSaveErrorMessage(validation.message);
      return;
    }

    setEditSaving(true);
    setEditSaveStatus(null);
    setEditSaveErrorMessage('');

    try {
      await testDbConnection(editingConn);

      await api.put(`/api/v1/db-connections/${editingConn.id}`, {
          provider: editingConn.provider,
          name: editingConn.name,
          host: editingConn.host,
          port: parseInt(editingConn.port, 10),
          db_name: editingConn.db_name,
          username: editingConn.username,
          password: editingConn.password_encrypted,
      });

      setEditSaveStatus('success');
      fetchConnections();

      setTimeout(() => {
        setEditingConn(null);
        setEditTestStatus(null);
        setEditSaveStatus(null);
      }, 1000);
    } catch (err: any) {
      setEditSaveStatus('error');
      const errMsg = err.response?.data?.detail || err.message || 'Failed to verify or update database connection';
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
            {t(m, 'file_manager.sql_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.sql_desc')}
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
            {t(m, 'file_manager.sql_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.sql_desc')}
          </p>
        </div>
        
        <div className="enterprise-panel p-12 md:p-16 text-center flex flex-col items-center max-w-3xl mx-auto">
          <div className="w-14 h-14 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-400 mb-6">
            <Lock className="w-7 h-7" />
          </div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-3">
            {t(m, 'file_manager.sql_locked_title')}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed mb-8 max-w-md">
            {t(m, 'file_manager.sql_locked_desc')}
          </p>
          <button
            onClick={() => router.push(localePath('/settings', routing))}
            className="px-6 py-3 btn-primary text-xs"
          >
            {t(m, 'file_manager.upgrade_pro_btn')}
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
            {t(m, 'file_manager.sql_connections')}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t(m, 'file_manager.sql_desc')}
          </p>
        </div>
        {!showAddModal && (
          <button
            onClick={openAddModal}
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
            ? 'Database credentials are encrypted at rest and transmitted over TLS. Connections are isolated to your account.'
            : 'ข้อมูลเข้าสู่ระบบฐานข้อมูลถูกเข้ารหัสเมื่อจัดเก็บและส่งผ่าน TLS การเชื่อมต่อแยกอยู่ในบัญชีของคุณเท่านั้น'}
        </span>
      </div>

      {showAddModal && (
        <DbAddConnectionModal
          isEn={isEn}
          m={m}
          step={addStep}
          provider={provider}
          onSelectProvider={selectProviderForAdd}
          onBackToGrid={() => setAddStep('pick')}
          onClose={closeAddModal}
          onTest={handleTestConnection}
          onSave={handleSaveConnection}
          testing={testing}
          saving={saving}
          testStatus={testStatus}
          testErrorMessage={testErrorMessage}
          saveStatus={saveStatus}
          saveErrorMessage={saveErrorMessage}
          canSave={testPassed}
          form={{
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
          }}
        />
      )}

      {!showAddModal && (
        <div className="space-y-4">
          {syncSuccess && (
            <div className="p-4 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 text-green-700 dark:text-green-400 text-xs font-medium rounded-lg flex items-center gap-2">
              <CheckCircle className="w-4 h-4" />
              <span>{isEn ? 'Data synchronized successfully! Check your Files list.' : 'ดึงข้อมูลจาก SQL สำเร็จ! กรุณาตรวจสอบที่รายการไฟล์ของคุณ'}</span>
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
                      <DbProviderLogo providerId={conn.provider} className="w-10 h-10" compact />
                      <div className="min-w-0">
                        <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate">{conn.name}</h4>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate flex items-center gap-1.5 font-sans mt-0.5">
                          <span className="font-bold text-[10px] bg-slate-100 dark:bg-slate-900/60 px-1.5 py-0.5 rounded text-slate-650 dark:text-slate-300">
                            {getProviderLabel(conn.provider)}
                          </span>
                          {conn.host}:{conn.port} ({conn.db_name})
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
                          onClick={() => setSyncModal({
                            show: true,
                            connId: conn.id,
                            queryType: 'table',
                            target: '',
                            format: 'csv',
                            overwrite: true,
                          })}
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
                <Database className="w-14 h-14 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                <h4 className="text-base font-bold text-slate-900 dark:text-slate-200 mb-2">
                  {t(m, 'file_manager.no_sql')}
                </h4>
                <p className="text-sm text-slate-500 dark:text-slate-455 mb-8 max-w-lg mx-auto font-sans leading-relaxed">
                  {t(m, 'file_manager.no_sql_desc')}
                </p>
                <button
                  onClick={openAddModal}
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

      {/* Modal ดึงข้อมูล SQL */}
      {syncModal.show && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="app-modal w-full max-w-lg p-6">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">
              {isEn ? 'SQL Database Synchronization' : 'ดึงข้อมูลจาก SQL Database'}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-6 leading-relaxed font-sans">
              {isEn 
                ? 'Specify a table name or write a custom SELECT query to extract and save database contents.'
                : 'ระบุชื่อตารางหรือเขียนคำสั่ง SELECT query เพื่อดึงข้อมูลออกไปบันทึก'}
            </p>

            <div className="space-y-4 mb-6">
              {/* Type selector */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1.5 px-1">
                  {isEn ? 'Extraction Method' : 'รูปแบบการดึงข้อมูล'}
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setSyncModal({ ...syncModal, queryType: 'table' })}
                    className={`flex-1 py-2 text-xs font-medium rounded-lg border transition-colors ${
                      syncModal.queryType === 'table' 
                        ? 'border-[#d97706] bg-slate-50 dark:bg-slate-800/50 text-[#d97706]' 
                        : 'border-slate-200 dark:border-slate-800 text-slate-500'
                    }`}
                  >
                    {isEn ? 'Table Name' : 'ระบุชื่อตาราง'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSyncModal({ ...syncModal, queryType: 'query' })}
                    className={`flex-1 py-2 text-xs font-medium rounded-lg border transition-colors ${
                      syncModal.queryType === 'query' 
                        ? 'border-[#d97706] bg-slate-50 dark:bg-slate-800/50 text-[#d97706]' 
                        : 'border-slate-200 dark:border-slate-800 text-slate-500'
                    }`}
                  >
                    {isEn ? 'Custom SQL Query' : 'คำสั่ง SQL Query'}
                  </button>
                </div>
              </div>

              {/* Input field */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1.5 px-1">
                  {syncModal.queryType === 'table' 
                    ? (isEn ? 'Table Name' : 'ชื่อตาราง') 
                    : (isEn ? 'SQL Query' : 'คำสั่ง SQL SELECT')}
                </label>
                {syncModal.queryType === 'table' ? (
                  <input
                    type="text"
                    value={syncModal.target}
                    onChange={(e) => setSyncModal({ ...syncModal, target: e.target.value })}
                    placeholder="e.g. users"
                    className="app-input w-full rounded-lg p-3 text-sm"
                  />
                ) : (
                  <textarea
                    rows={4}
                    value={syncModal.target}
                    onChange={(e) => setSyncModal({ ...syncModal, target: e.target.value })}
                    placeholder="SELECT * FROM orders WHERE amount > 100 LIMIT 1000"
                    className="app-input w-full rounded-lg p-3 text-sm font-mono resize-none"
                  />
                )}
              </div>

              {/* Format selection */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1.5 px-1">
                  {isEn ? 'Output File Format' : 'ฟอร์แมตไฟล์ปลายทาง'}
                </label>
                <div className="flex gap-2">
                  {['csv', 'json'].map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setSyncModal({ ...syncModal, format: f })}
                      className={`px-4 py-2 text-xs font-medium rounded-lg border transition-colors uppercase ${
                        syncModal.format === f
                          ? 'border-[#d97706] bg-slate-50 dark:bg-slate-800/50 text-[#d97706]'
                          : 'border-slate-200 dark:border-slate-800 text-slate-500'
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Overwrite option */}
              <div className="flex items-center gap-2 px-1">
                <input
                  type="checkbox"
                  id="overwrite-db"
                  checked={syncModal.overwrite}
                  onChange={(e) => setSyncModal({ ...syncModal, overwrite: e.target.checked })}
                  className="rounded border-slate-300 dark:border-slate-700 text-[#d97706] focus:ring-[#d97706]"
                />
                <label htmlFor="overwrite-db" className="text-xs font-bold text-slate-700 dark:text-slate-350 cursor-pointer">
                  {isEn ? 'Overwrite existing file on sync' : 'บันทึกทับไฟล์เดิมในการดึงข้อมูลครั้งต่อไป'}
                </label>
              </div>
            </div>

            <div className="flex justify-end gap-3 font-sans">
              <button
                onClick={() => setSyncModal({ ...syncModal, show: false })}
                className="px-5 py-2.5 btn-secondary text-xs"
              >
                {t(m, 'chat.cancel')}
              </button>
              <button
                onClick={handleSyncDb}
                className="px-6 py-2.5 btn-primary text-xs flex items-center gap-2"
              >
                <RefreshCw size={14} className={syncingId !== null ? 'animate-spin' : ''} />
                {isEn ? 'Extract & Sync' : 'ดึงข้อมูล'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Edit Connection Modal */}
      {editingConn && (
        <div className="fixed inset-0 z-[160] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm font-sans">
          <div className="app-modal w-full max-w-xl p-6 md:p-8 flex flex-col relative overflow-y-auto max-h-[90vh] no-scrollbar">
            <div className="flex items-center justify-between mb-6 w-full">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-base">
                {isEn ? 'Edit Database Connection' : 'แก้ไขการเชื่อมต่อฐานข้อมูล'}
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
                  {t(m, 'file_manager.sql_test_ok')}
                </h3>
              </div>
            )}

            {editTestStatus === 'error' && (
              <div className="mb-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 p-4 rounded-lg flex flex-col items-center text-center">
                <ShieldAlert className="w-8 h-8 text-red-500 mb-2" />
                <p className="text-[10px] text-red-650 dark:text-red-400 font-sans leading-relaxed">
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
                <p className="text-[10px] text-red-650 dark:text-red-400 font-sans leading-relaxed">
                  {editSaveErrorMessage}
                </p>
              </div>
            )}

            <form onSubmit={handleUpdateConnection} className="space-y-4">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 mb-2">
                <DbProviderLogo providerId={editingConn.provider} className="w-10 h-10" compact />
                <span className="text-xs font-semibold text-slate-800 dark:text-slate-100">
                  {getProviderLabel(editingConn.provider)}
                </span>
              </div>

              <DbConnectionFormFields
                isEn={isEn}
                m={m}
                provider={editingConn.provider}
                name={editingConn.name}
                setName={(value) => setEditingConn({ ...editingConn, name: value })}
                host={editingConn.host}
                setHost={(value) => setEditingConn({ ...editingConn, host: value })}
                port={String(editingConn.port ?? '')}
                setPort={(value) => setEditingConn({ ...editingConn, port: value })}
                dbName={editingConn.db_name}
                setDbName={(value) => setEditingConn({ ...editingConn, db_name: value })}
                username={editingConn.username}
                setUsername={(value) => setEditingConn({ ...editingConn, username: value })}
                password={editingConn.password_encrypted || ''}
                setPassword={(value) => setEditingConn({ ...editingConn, password_encrypted: value })}
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
                      {t(m, 'file_manager.testing_conn')}
                    </>
                  ) : (
                    t(m, 'file_manager.test_sql')
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
            ? 'This database connection will be permanently removed and cannot be recovered.'
            : 'การเชื่อมต่อฐานข้อมูลนี้จะถูกลบอย่างถาวร และกู้คืนไม่ได้'
        }
        confirmButtonText={isEn ? 'Delete connection' : 'ลบการเชื่อมต่อ'}
        cancelButtonText={t(m, 'chat.cancel')}
      />
    </div>
  );
};

export default DatabaseConnectView;
