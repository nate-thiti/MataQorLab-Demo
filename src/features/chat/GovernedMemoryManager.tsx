// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Plus, RefreshCw, Save, Trash2 } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env.js';
import AppSelect from '../../components/ui/AppSelect';

const emptyDraft = {
  title: '', content: '', memory_type: 'business_definition',
  scope: 'personal', confidence: 1,
};

const MEMORY_TYPES = [
  'business_definition',
  'kpi_formula',
  'terminology',
  'policy',
  'reporting_convention',
  'dataset_fact',
  'preference',
];

const MEMBER_ROLES = ['admin', 'reviewer', 'member'];

export default function GovernedMemoryManager({ open, userId, isEn, showOrganizationAdmin = true }) {
  const [context, setContext] = useState({ organizations: [], workspaces: [] });
  const [organizationId, setOrganizationId] = useState('');
  const [workspaceId, setWorkspaceId] = useState('');
  const [memories, setMemories] = useState([]);
  const [draft, setDraft] = useState(emptyDraft);
  const [organizationName, setOrganizationName] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [memberUserId, setMemberUserId] = useState('');
  const [memberRole, setMemberRole] = useState('member');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState({});

  const request = useCallback(async (path, init = {}) => {
    const response = await authFetch(`${getPublicApiUrl()}/api/v1${path}`, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Request failed');
    return payload;
  }, []);

  const loadContext = useCallback(async () => {
    if (!open || !userId) return;
    const payload = await request('/governance/context', { method: 'GET' });
    setContext(payload);
    setOrganizationId((current) => current || payload.organizations?.[0]?.organization_id || '');
  }, [open, request, userId]);

  const loadMemories = useCallback(async () => {
    if (!open || !userId) return;
    const query = new URLSearchParams();
    if (organizationId) query.set('organization_id', organizationId);
    if (workspaceId) query.set('workspace_id', workspaceId);
    const payload = await request(`/governance/memories?${query}`, { method: 'GET' });
    setMemories(payload.memories || []);
  }, [open, organizationId, request, userId, workspaceId]);

  useEffect(() => { loadContext().catch((err) => setError(err.message)); }, [loadContext]);
  useEffect(() => { loadMemories().catch((err) => setError(err.message)); }, [loadMemories]);

  const availableWorkspaces = useMemo(
    () => context.workspaces.filter((item) => item.organization_id === organizationId),
    [context.workspaces, organizationId],
  );
  const selectedMembership = context.organizations.find((item) => item.organization_id === organizationId);
  const canReview = ['owner', 'admin', 'reviewer'].includes(selectedMembership?.role);

  const organizationOptions = useMemo(() => ([
    { value: '', label: isEn ? 'Personal memory' : 'ความจำส่วนตัว' },
    ...context.organizations.map((item) => ({
      value: item.organization_id,
      label: `${item.organizations?.name || item.organization_id} · ${item.role}`,
    })),
  ]), [context.organizations, isEn]);

  const workspaceOptions = useMemo(() => ([
    { value: '', label: isEn ? 'Organization-wide' : 'ทั้งองค์กร' },
    ...availableWorkspaces.map((item) => ({
      value: item.id,
      label: item.name,
    })),
  ]), [availableWorkspaces, isEn]);

  const memberRoleOptions = useMemo(
    () => MEMBER_ROLES.map((role) => ({ value: role, label: role })),
    [],
  );

  const memoryTypeOptions = useMemo(
    () => MEMORY_TYPES.map((type) => ({
      value: type,
      label: type.replaceAll('_', ' '),
    })),
    [],
  );

  const selectButtonClass = 'px-3 py-2 text-xs';

  const createOrganization = async () => {
    if (!organizationName.trim()) return;
    setBusy('organization');
    try {
      await request('/governance/organizations', { body: { name: organizationName } });
      setOrganizationName('');
      await loadContext();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const createWorkspace = async () => {
    if (!workspaceName.trim() || !organizationId) return;
    setBusy('workspace');
    try {
      await request('/governance/workspaces', {
        body: { organization_id: organizationId, name: workspaceName },
      });
      setWorkspaceName('');
      await loadContext();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const addMember = async () => {
    if (!memberUserId.trim() || !organizationId) return;
    setBusy('member');
    try {
      await request('/governance/members', {
        body: {
          organization_id: organizationId,
          workspace_id: workspaceId || null,
          member_user_id: memberUserId.trim(),
          role: memberRole,
        },
      });
      setMemberUserId('');
      await loadContext();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const saveMemory = async () => {
    setBusy('memory');
    try {
      const scope = organizationId ? (workspaceId ? 'workspace' : 'organization') : 'personal';
      await request('/governance/memories', {
        body: {
          ...draft, scope,
          organization_id: organizationId || null,
          workspace_id: workspaceId || null,
        },
      });
      setDraft(emptyDraft);
      await loadMemories();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const review = async (memoryId, decision) => {
    setBusy(memoryId);
    try {
      await request('/governance/memories/review', {
        body: { memory_id: memoryId, decision },
      });
      await loadMemories();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const archive = async (memoryId) => {
    setBusy(memoryId);
    try {
      await request('/governance/memories', {
        method: 'DELETE', body: { memory_id: memoryId },
      });
      await loadMemories();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const loadHistory = async (memoryId) => {
    setBusy(`history:${memoryId}`);
    try {
      const payload = await request(`/governance/memories/${memoryId}/history`, { method: 'GET' });
      setHistory((current) => ({ ...current, [memoryId]: payload }));
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const restore = async (memoryId, revisionId) => {
    setBusy(`restore:${memoryId}`);
    try {
      await request('/governance/memories/restore', {
        body: { memory_id: memoryId, revision_id: revisionId },
      });
      setHistory((current) => ({ ...current, [memoryId]: null }));
      await loadMemories();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  return (
    <section className="space-y-4 rounded-xl border border-stone-200 bg-stone-50/50 p-4 dark:border-stone-700 dark:bg-stone-900/40">
      <div>
        <h3 className="text-sm font-semibold">{isEn ? 'Saved definitions' : 'นิยามที่บันทึกไว้'}</h3>
        <p className="mt-1 text-[11px] text-slate-500">{isEn ? 'Personal notes save immediately. Shared company memory enters analysis context only after reviewer approval.' : 'บันทึกส่วนตัวใช้ได้ทันที ความจำองค์กรจะเข้าบริบทการวิเคราะห์หลัง Reviewer อนุมัติเท่านั้น'}</p>
      </div>
      {error && <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700">{error}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        <AppSelect
          value={organizationId}
          onChange={(next) => {
            setOrganizationId(next);
            setWorkspaceId('');
          }}
          options={organizationOptions}
          buttonClassName={selectButtonClass}
          aria-label={isEn ? 'Memory scope' : 'ขอบเขตความจำ'}
        />
        <AppSelect
          value={workspaceId}
          disabled={!organizationId}
          onChange={setWorkspaceId}
          options={workspaceOptions}
          buttonClassName={selectButtonClass}
          aria-label={isEn ? 'Workspace' : 'พื้นที่ทำงาน'}
        />
      </div>
      {!context.organizations.length && showOrganizationAdmin && (
        <div className="flex gap-2">
          <input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder={isEn ? 'Organization name' : 'ชื่อองค์กร'} className="app-input min-w-0 flex-1 px-3 py-2 text-xs" />
          <button type="button" onClick={createOrganization} className="btn-secondary px-3 text-xs"><Plus size={13} /> {isEn ? 'Create' : 'สร้าง'}</button>
        </div>
      )}
      {showOrganizationAdmin && organizationId && ['owner', 'admin'].includes(selectedMembership?.role) && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder={isEn ? 'New workspace' : 'Workspace ใหม่'} className="app-input min-w-0 flex-1 px-3 py-2 text-xs" />
            <button type="button" onClick={createWorkspace} className="btn-secondary px-3 text-xs"><Plus size={13} /> {isEn ? 'Workspace' : 'พื้นที่ทำงาน'}</button>
          </div>
          <div className="grid gap-2 sm:grid-cols-[1fr_140px_auto]">
            <input value={memberUserId} onChange={(event) => setMemberUserId(event.target.value)} placeholder={isEn ? 'Member account UUID' : 'Account UUID ของสมาชิก'} className="app-input px-3 py-2 text-xs" />
            <AppSelect
              value={memberRole}
              onChange={setMemberRole}
              options={memberRoleOptions}
              buttonClassName={selectButtonClass}
              aria-label={isEn ? 'Member role' : 'บทบาทสมาชิก'}
            />
            <button type="button" onClick={addMember} disabled={!memberUserId.trim()} className="btn-secondary px-3 text-xs">{isEn ? 'Add member' : 'เพิ่มสมาชิก'}</button>
          </div>
        </div>
      )}
      {!showOrganizationAdmin && (
        <p className="text-[11px] text-slate-500">
          {isEn
            ? 'Manage organizations, members, and approvals in Settings → Organization.'
            : 'จัดการองค์กร สมาชิก และการอนุมัติได้ที่ Settings → Organization'}
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder={isEn ? 'Memory title' : 'ชื่อความจำ'} className="app-input px-3 py-2 text-xs" />
        <AppSelect
          value={draft.memory_type}
          onChange={(next) => setDraft((current) => ({ ...current, memory_type: next }))}
          options={memoryTypeOptions}
          buttonClassName={selectButtonClass}
          aria-label={isEn ? 'Memory type' : 'ประเภทความจำ'}
        />
        <textarea value={draft.content} onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))} placeholder={isEn ? 'Approved business definition, formula or policy' : 'นิยาม สูตร หรือนโยบายธุรกิจ'} className="app-input min-h-20 px-3 py-2 text-xs sm:col-span-2" />
      </div>
      <button type="button" disabled={!draft.title.trim() || !draft.content.trim() || busy === 'memory'} onClick={saveMemory} className="btn-primary inline-flex items-center gap-1.5 px-3 py-2 text-xs"><Save size={13} />{organizationId ? (isEn ? 'Submit for approval' : 'ส่งเพื่ออนุมัติ') : (isEn ? 'Save personal memory' : 'บันทึกความจำส่วนตัว')}</button>
      <div className="space-y-2">
        {memories.map((memory) => (
          <article key={memory.id} className="rounded-lg border border-slate-200 bg-white p-3 text-xs dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-start justify-between gap-3">
              <div><p className="font-semibold">{memory.title}</p><p className="mt-1 text-[10px] text-slate-400">{memory.memory_type} · {memory.scope} · v{memory.version} · {memory.status}</p></div>
              <div className="flex gap-1">
                {canReview && memory.status === 'pending' && <><button type="button" title={isEn ? 'Approve' : 'อนุมัติ'} onClick={() => review(memory.id, 'approve')} className="p-1.5 text-emerald-600"><Check size={13} /></button><button type="button" title={isEn ? 'Reject' : 'ปฏิเสธ'} onClick={() => review(memory.id, 'reject')} className="p-1.5 text-amber-600"><RefreshCw size={13} /></button></>}
                <button type="button" title={isEn ? 'History' : 'ประวัติ'} onClick={() => loadHistory(memory.id)} className="p-1.5 text-slate-500"><RefreshCw size={13} /></button>
                <button type="button" title={isEn ? 'Archive' : 'เก็บถาวร'} onClick={() => archive(memory.id)} className="p-1.5 text-red-500"><Trash2 size={13} /></button>
              </div>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-slate-600 dark:text-slate-300">{memory.content}</p>
            {history[memory.id] && (
              <div className="mt-3 space-y-1 border-t border-slate-100 pt-2 dark:border-slate-800">
                {(history[memory.id].revisions || []).map((revision) => (
                  <div key={revision.id} className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
                    <span>v{revision.version} · {revision.change_type} · {new Date(revision.created_at).toLocaleString()}</span>
                    {revision.version !== memory.version && <button type="button" onClick={() => restore(memory.id, revision.id)} className="text-amber-700">{isEn ? 'Restore' : 'กู้คืน'}</button>}
                  </div>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
