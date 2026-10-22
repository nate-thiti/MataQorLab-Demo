// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, Check, Pencil, Plus, RefreshCw, Trash2 } from '@/components/icons';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env.js';
import AppSelect from '../ui/AppSelect';

export default function OrganizationWorkspaceSettings({ userId, isEn = false, planName = 'Free' }) {
  const [context, setContext] = useState({ organizations: [], workspaces: [] });
  const [organizationId, setOrganizationId] = useState('');
  const [workspaceId, setWorkspaceId] = useState('');
  const [memories, setMemories] = useState([]);
  const [organizationName, setOrganizationName] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [editOrganizationName, setEditOrganizationName] = useState('');
  const [editWorkspaceName, setEditWorkspaceName] = useState('');
  const [memberUserId, setMemberUserId] = useState('');
  const [memberRole, setMemberRole] = useState('member');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  // Company (business) plans only — individual Free/Plus/Pro do not get org admin tooling.
  const isCompanyPlan = String(planName || '').toLowerCase().includes('enterprise');

  const request = useCallback(async (path, init = {}) => {
    const response = await authFetch(`${getPublicApiUrl()}/api/v1${path}`, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Request failed');
    return payload;
  }, []);

  const loadContext = useCallback(async () => {
    if (!userId) return;
    const payload = await request('/governance/context', { method: 'GET' });
    setContext(payload);
    setOrganizationId((current) => {
      if (current && payload.organizations?.some((item) => item.organization_id === current)) {
        return current;
      }
      return payload.organizations?.[0]?.organization_id || '';
    });
  }, [request, userId]);

  const loadMemories = useCallback(async () => {
    if (!userId || !organizationId) {
      setMemories([]);
      return;
    }
    const query = new URLSearchParams({ organization_id: organizationId });
    if (workspaceId) query.set('workspace_id', workspaceId);
    const payload = await request(`/governance/memories?${query}`, { method: 'GET' });
    setMemories(payload.memories || []);
  }, [organizationId, request, userId, workspaceId]);

  useEffect(() => {
    loadContext().catch((err) => setError(err.message));
  }, [loadContext]);

  useEffect(() => {
    loadMemories().catch((err) => setError(err.message));
  }, [loadMemories]);

  const availableWorkspaces = useMemo(
    () => context.workspaces.filter((item) => item.organization_id === organizationId),
    [context.workspaces, organizationId],
  );
  const selectedMembership = context.organizations.find((item) => item.organization_id === organizationId);
  const selectedOrganizationName = selectedMembership?.organizations?.name || '';
  const selectedWorkspace = availableWorkspaces.find((item) => item.id === workspaceId);
  const canAdmin = ['owner', 'admin'].includes(selectedMembership?.role);
  const canOwner = selectedMembership?.role === 'owner';
  const canReview = ['owner', 'admin', 'reviewer'].includes(selectedMembership?.role);
  const pendingMemories = memories.filter((item) => item.status === 'pending' && item.scope !== 'personal');

  useEffect(() => {
    setEditOrganizationName(selectedOrganizationName);
  }, [selectedOrganizationName, organizationId]);

  useEffect(() => {
    setEditWorkspaceName(selectedWorkspace?.name || '');
  }, [selectedWorkspace?.name, workspaceId]);

  useEffect(() => {
    if (workspaceId && !availableWorkspaces.some((item) => item.id === workspaceId)) {
      setWorkspaceId('');
    }
  }, [availableWorkspaces, workspaceId]);

  const organizationOptions = useMemo(() => ([
    { value: '', label: isEn ? 'Select organization' : 'เลือกองค์กร' },
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

  const roleOptions = useMemo(() => (
    ['admin', 'reviewer', 'member'].map((role) => ({ value: role, label: role }))
  ), []);

  const createOrganization = async () => {
    if (!organizationName.trim()) return;
    setBusy('organization');
    setError('');
    try {
      const payload = await request('/governance/organizations', { body: { name: organizationName } });
      setOrganizationName('');
      await loadContext();
      if (payload.organization?.id) setOrganizationId(payload.organization.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const createWorkspace = async () => {
    if (!workspaceName.trim() || !organizationId) return;
    setBusy('workspace');
    setError('');
    try {
      const payload = await request('/governance/workspaces', {
        body: { organization_id: organizationId, name: workspaceName },
      });
      setWorkspaceName('');
      await loadContext();
      if (payload.workspace?.id) setWorkspaceId(payload.workspace.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const renameOrganization = async () => {
    if (!organizationId || !editOrganizationName.trim() || !canAdmin) return;
    if (editOrganizationName.trim() === selectedOrganizationName) return;
    setBusy('rename-org');
    setError('');
    try {
      await request('/governance/organizations', {
        method: 'PATCH',
        body: { organization_id: organizationId, name: editOrganizationName.trim() },
      });
      await loadContext();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const deleteOrganization = async () => {
    if (!organizationId || !canOwner) return;
    const label = selectedOrganizationName || organizationId;
    const confirmed = window.confirm(
      isEn
        ? `Delete organization "${label}"? All workspaces, members, and company memory will be permanently removed.`
        : `ลบองค์กร "${label}"? พื้นที่ทำงาน สมาชิก และความจำองค์กรจะถูกลบถาวร`,
    );
    if (!confirmed) return;
    setBusy('delete-org');
    setError('');
    try {
      await request('/governance/organizations', {
        method: 'DELETE',
        body: { organization_id: organizationId },
      });
      setOrganizationId('');
      setWorkspaceId('');
      await loadContext();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const renameWorkspace = async () => {
    if (!workspaceId || !editWorkspaceName.trim() || !canAdmin) return;
    if (editWorkspaceName.trim() === selectedWorkspace?.name) return;
    setBusy('rename-workspace');
    setError('');
    try {
      await request('/governance/workspaces', {
        method: 'PATCH',
        body: { workspace_id: workspaceId, name: editWorkspaceName.trim() },
      });
      await loadContext();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const deleteWorkspace = async () => {
    if (!workspaceId || !canAdmin) return;
    const label = selectedWorkspace?.name || workspaceId;
    const confirmed = window.confirm(
      isEn
        ? `Delete workspace "${label}"? Workspace memory and memberships will be permanently removed.`
        : `ลบพื้นที่ทำงาน "${label}"? ความจำและสมาชิกในพื้นที่นี้จะถูกลบถาวร`,
    );
    if (!confirmed) return;
    setBusy('delete-workspace');
    setError('');
    try {
      await request('/governance/workspaces', {
        method: 'DELETE',
        body: { workspace_id: workspaceId },
      });
      setWorkspaceId('');
      await loadContext();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const addMember = async () => {
    if (!memberUserId.trim() || !organizationId) return;
    setBusy('member');
    setError('');
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
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const review = async (memoryId, decision) => {
    setBusy(memoryId);
    setError('');
    try {
      await request('/governance/memories/review', {
        body: { memory_id: memoryId, decision },
      });
      await loadMemories();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const archive = async (memoryId) => {
    setBusy(memoryId);
    setError('');
    try {
      await request('/governance/memories', {
        method: 'DELETE',
        body: { memory_id: memoryId },
      });
      await loadMemories();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const fieldClass = 'app-input w-full px-3 py-2.5 text-sm';

  return (
    <div id="settings-organization" className="enterprise-panel space-y-5 scroll-mt-24 p-6 md:p-8">
      <div className="flex items-center gap-3 border-b border-slate-200/80 pb-4 dark:border-white/10">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
          <Building2 size={18} strokeWidth={1.6} />
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
            {isEn ? 'Organization & workspace' : 'องค์กรและพื้นที่ทำงาน'}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {isEn
              ? 'Manage members, roles, and company memory approvals for shared analysis.'
              : 'จัดการสมาชิก บทบาท และการอนุมัติความจำองค์กรสำหรับการวิเคราะห์ร่วม'}
          </p>
        </div>
      </div>

      {!isCompanyPlan && !context.organizations.length ? (
        <p className="rounded-xl border border-dashed border-slate-200/80 bg-slate-50/60 p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-zinc-900/40 dark:text-slate-400">
          {isEn
            ? 'Organization workspaces are available on the company (Enterprise) plan. You can still keep personal analysis memory from Chat.'
            : 'พื้นที่องค์กรใช้ได้ในแผนบริษัท (Enterprise) คุณยังใช้ความจำส่วนตัวจาก Chat ได้ตามปกติ'}
        </p>
      ) : null}

      {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {isEn ? 'Organization' : 'องค์กร'}
          <AppSelect
            className="mt-1.5"
            value={organizationId}
            onChange={(next) => {
              setOrganizationId(next);
              setWorkspaceId('');
            }}
            options={organizationOptions}
            aria-label={isEn ? 'Organization' : 'องค์กร'}
          />
        </label>
        <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {isEn ? 'Workspace' : 'พื้นที่ทำงาน'}
          <AppSelect
            className="mt-1.5"
            value={workspaceId}
            onChange={setWorkspaceId}
            options={workspaceOptions}
            disabled={!organizationId}
            aria-label={isEn ? 'Workspace' : 'พื้นที่ทำงาน'}
          />
        </label>
      </div>

      {organizationId && canAdmin && (
        <div className="space-y-4 rounded-xl border border-slate-200/80 bg-white/70 p-4 dark:border-slate-700 dark:bg-zinc-950/40">
          <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
            {isEn ? 'Edit or delete' : 'แก้ไขหรือลบ'}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={editOrganizationName}
              onChange={(event) => setEditOrganizationName(event.target.value)}
              placeholder={isEn ? 'Organization name' : 'ชื่อองค์กร'}
              className={`min-w-0 flex-1 ${fieldClass}`}
            />
            <button
              type="button"
              onClick={renameOrganization}
              disabled={busy === 'rename-org' || !editOrganizationName.trim() || editOrganizationName.trim() === selectedOrganizationName}
              className="btn-secondary inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs"
            >
              <Pencil size={13} /> {isEn ? 'Rename' : 'เปลี่ยนชื่อ'}
            </button>
            {canOwner && (
              <button
                type="button"
                onClick={deleteOrganization}
                disabled={busy === 'delete-org'}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-200 px-3 py-2.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/30"
              >
                <Trash2 size={13} /> {isEn ? 'Delete org' : 'ลบองค์กร'}
              </button>
            )}
          </div>
          {workspaceId ? (
            <div className="flex flex-col gap-2 border-t border-slate-200/70 pt-4 sm:flex-row dark:border-slate-700">
              <input
                value={editWorkspaceName}
                onChange={(event) => setEditWorkspaceName(event.target.value)}
                placeholder={isEn ? 'Workspace name' : 'ชื่อพื้นที่ทำงาน'}
                className={`min-w-0 flex-1 ${fieldClass}`}
              />
              <button
                type="button"
                onClick={renameWorkspace}
                disabled={busy === 'rename-workspace' || !editWorkspaceName.trim() || editWorkspaceName.trim() === selectedWorkspace?.name}
                className="btn-secondary inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs"
              >
                <Pencil size={13} /> {isEn ? 'Rename' : 'เปลี่ยนชื่อ'}
              </button>
              <button
                type="button"
                onClick={deleteWorkspace}
                disabled={busy === 'delete-workspace'}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-200 px-3 py-2.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/30"
              >
                <Trash2 size={13} /> {isEn ? 'Delete workspace' : 'ลบพื้นที่'}
              </button>
            </div>
          ) : (
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              {isEn
                ? 'Select a workspace above to rename or delete it.'
                : 'เลือกพื้นที่ทำงานด้านบนเพื่อเปลี่ยนชื่อหรือลบ'}
            </p>
          )}
        </div>
      )}

      {(isCompanyPlan || canAdmin || !context.organizations.length) && (
        <div className="space-y-4 rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-zinc-900/45">
          <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
            {isEn ? 'Create & invite' : 'สร้างและเชิญสมาชิก'}
          </p>
          {(isCompanyPlan || !context.organizations.length) && (
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              placeholder={isEn ? 'Organization name' : 'ชื่อองค์กร'}
              className={`min-w-0 flex-1 ${fieldClass}`}
            />
            <button type="button" onClick={createOrganization} disabled={busy === 'organization' || !isCompanyPlan} className="btn-secondary inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs">
              <Plus size={13} /> {isEn ? 'Create' : 'สร้าง'}
            </button>
          </div>
          )}
          {organizationId && canAdmin && (
            <>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.target.value)}
                  placeholder={isEn ? 'New workspace' : 'Workspace ใหม่'}
                  className={`min-w-0 flex-1 ${fieldClass}`}
                />
                <button type="button" onClick={createWorkspace} disabled={busy === 'workspace'} className="btn-secondary inline-flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs">
                  <Plus size={13} /> {isEn ? 'Workspace' : 'พื้นที่ทำงาน'}
                </button>
              </div>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_140px_auto]">
                <input
                  value={memberUserId}
                  onChange={(event) => setMemberUserId(event.target.value)}
                  placeholder={isEn ? 'Member account UUID' : 'Account UUID ของสมาชิก'}
                  className={fieldClass}
                />
                <AppSelect
                  value={memberRole}
                  onChange={setMemberRole}
                  options={roleOptions}
                  aria-label={isEn ? 'Member role' : 'บทบาทสมาชิก'}
                />
                <button type="button" onClick={addMember} disabled={!memberUserId.trim() || busy === 'member'} className="btn-secondary px-3 py-2.5 text-xs">
                  {isEn ? 'Add member' : 'เพิ่มสมาชิก'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
            {isEn ? 'Company memory awaiting approval' : 'ความจำองค์กรรออนุมัติ'}
          </p>
          <button type="button" onClick={() => loadMemories().catch((err) => setError(err.message))} className="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition-colors hover:border-amber-300 hover:text-amber-700 dark:border-slate-700 dark:hover:border-amber-800 dark:hover:text-amber-300" title={isEn ? 'Refresh' : 'รีเฟรช'}>
            <RefreshCw size={13} />
          </button>
        </div>
        {!organizationId ? (
          <p className="text-xs text-slate-500">{isEn ? 'Select an organization to review shared memory.' : 'เลือกองค์กรเพื่อตรวจความจำที่แชร์'}</p>
        ) : pendingMemories.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-200/80 bg-white/50 p-4 text-xs text-slate-500 dark:border-slate-700 dark:bg-zinc-950/30">
            {isEn ? 'No pending company memory.' : 'ไม่มีความจำองค์กรที่รออนุมัติ'}
          </p>
        ) : (
          pendingMemories.map((memory) => (
            <article key={memory.id} className="rounded-xl border border-slate-200/80 bg-white p-4 text-xs shadow-sm dark:border-slate-700 dark:bg-zinc-900/70">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-slate-800 dark:text-slate-100">{memory.title}</p>
                  <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-400">
                    {memory.memory_type} · {memory.scope} · v{memory.version}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  {canReview && (
                    <>
                      <button type="button" title={isEn ? 'Approve' : 'อนุมัติ'} onClick={() => review(memory.id, 'approve')} className="rounded-lg border border-emerald-200 p-1.5 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/30">
                        <Check size={13} />
                      </button>
                      <button type="button" title={isEn ? 'Reject' : 'ปฏิเสธ'} onClick={() => review(memory.id, 'reject')} className="rounded-lg border border-amber-200 p-1.5 text-amber-700 hover:bg-amber-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/30">
                        <RefreshCw size={13} />
                      </button>
                    </>
                  )}
                  {canAdmin && (
                    <button type="button" title={isEn ? 'Archive' : 'เก็บถาวร'} onClick={() => archive(memory.id)} className="rounded-lg border border-red-200 p-1.5 text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/30">
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap leading-relaxed text-slate-600 dark:text-slate-300">{memory.content}</p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
