// @ts-nocheck
import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, PanelLeftClose, MessageSquarePlus, FolderOpen, MoreVertical, Pin, Edit2, Trash2 } from '@/components/icons';
import { localePath } from '../utils/locale.js';
import { buildFilesPath } from '../utils/dashboardRoutes.js';
import { getProgressFillClass } from '../utils/progressColor.js';
import { formatQuotaResetTime } from '../utils/profileQuota.js';
import MQLogo from '../assets/MQ.svg';

const ChatSidebar = ({ 
  isSidebarOpen, 
  setIsSidebarOpen, 
  navigate, 
  routing, 
  isEn, 
  startNewChat, 
  conversations, 
  hasMoreConversations = false,
  loadingMoreConversations = false,
  loadMoreConversations,
  activeConversationId, 
  loadConversation, 
  triggerDeleteConversation, 
  pinnedConvIds = [],
  togglePinConversation,
  renameConversation,
  user, 
  userInitial, 
  plan, 
  tokensUsedToday = 0,
  tokensUsedThisWeek = 0,
  dailyResetAt = null,
  weeklyResetAt = null,
  timezone = 'UTC',
}) => {
  const [activeDropdownId, setActiveDropdownId] = useState<any>(null);
  const [editingId, setEditingId] = useState<any>(null);
  const [renameValue, setRenameValue] = useState('');
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setActiveDropdownId(null);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleStartRename = (conv) => {
    setEditingId(conv.id);
    setRenameValue(conv.title);
    setActiveDropdownId(null);
  };

  const handleSaveRename = (convId) => {
    if (renameValue.trim()) {
      renameConversation(convId, renameValue.trim());
    }
    setEditingId(null);
  };

  const handleKeyDown = (e, convId) => {
    if (e.key === 'Enter') {
      handleSaveRename(convId);
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  const renderUsageBar = (used, limit, label) => {
    const pct = Math.min((used / limit) * 100, 100);
    return (
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-[10px] font-medium text-slate-400 uppercase font-sans tracking-wide">{label}</span>
          <span className="text-[10px] font-medium text-slate-600 dark:text-slate-300 font-sans tabular-nums">
            {used.toLocaleString()} / {limit.toLocaleString()}
          </span>
        </div>
        <div className="progress-track h-1.5">
          <div className={getProgressFillClass(pct)} style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  const renderPlanUsage = () => {
    const planNameLower = (plan?.name || 'Free').toLowerCase();

    if (planNameLower.includes('enterprise')) {
      return (
        <div className="mt-4 px-1">
          {renderUsageBar(tokensUsedToday, 2000000, isEn ? 'Daily Tokens (Enterprise)' : 'โควตารายวัน (Enterprise)')}
        </div>
      );
    }
    if (planNameLower.includes('pro')) {
      return (
        <div className="mt-4 px-1">
          {renderUsageBar(tokensUsedToday, 1000000, isEn ? 'Daily Tokens (Pro)' : 'โควตารายวัน (Pro)')}
        </div>
      );
    }
    if (planNameLower.includes('plus')) {
      return (
        <div className="mt-4 px-1 space-y-3">
          {renderUsageBar(tokensUsedToday, 400000, isEn ? 'Daily Tokens' : 'โควตารายวัน')}
          {renderUsageBar(tokensUsedThisWeek, 2500000, isEn ? 'Weekly Tokens' : 'โควตารายสัปดาห์')}
        </div>
      );
    }
    return (
      <div className="mt-4 px-1">
        {renderUsageBar(tokensUsedThisWeek, 200000, isEn ? 'Weekly Tokens (Free)' : 'โควตารายสัปดาห์ (Free)')}
      </div>
    );
  };

  const formatResetLabel = (dateStr) => {
    if (!dateStr) return isEn ? 'Not scheduled' : 'ยังไม่กำหนด';
    return formatQuotaResetTime(dateStr, timezone, isEn ? 'en-US' : 'th-TH');
  };

  const planNameLower = (plan?.name || 'Free').toLowerCase();
  const hasProAccess = planNameLower.includes('pro') || planNameLower.includes('enterprise');
  const showDailyReset = planNameLower.includes('plus') || hasProAccess;
  const showWeeklyReset = !hasProAccess;

  return (
    <aside className={`chat-sidebar app-sidebar fixed inset-y-0 left-0 z-50 flex shrink-0 flex-col overflow-hidden transition-all duration-300 ease-in-out md:relative md:z-20 ${isSidebarOpen ? 'w-72 translate-x-0' : 'pointer-events-none -translate-x-full opacity-0 md:pointer-events-auto md:w-0 md:translate-x-0'}`}>
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-stone-200/80 px-3 dark:border-stone-800">
        <button
          onClick={() => navigate(localePath('/dashboard', routing))}
          className="group min-w-0 flex items-center gap-2.5 rounded-xl p-1.5 -ml-1.5 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 transition-colors"
          title={isEn ? 'Back to dashboard' : 'กลับหน้าหลัก'}
        >
          <span className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 shrink-0">
            <img src={MQLogo?.src || MQLogo} alt="MataQorLab" className="h-6 w-6 object-contain transition-opacity group-hover:opacity-0" />
            <ArrowLeft className="absolute h-4 w-4 text-slate-500 opacity-0 transition-opacity group-hover:opacity-100" strokeWidth={1.7} />
          </span>
          <span className="min-w-0 text-left">
            <span className="block truncate text-sm font-semibold text-slate-900 dark:text-slate-100">MataQorLab</span>
            <span className="block text-[9px] font-medium tracking-wide text-stone-500 dark:text-stone-400">{isEn ? 'Analysis' : 'พื้นที่วิเคราะห์'}</span>
          </span>
        </button>
        <button 
          onClick={() => setIsSidebarOpen(false)}
          className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:text-slate-200 dark:hover:bg-slate-800 md:hidden flex-shrink-0"
          title={isEn ? 'Close sidebar' : 'ปิดเมนู'}
        >
          <PanelLeftClose size={20} strokeWidth={1.5} />
        </button>
      </div>
      
      <div className="p-3 space-y-2 border-b border-slate-200/80 dark:border-slate-800">
        <button 
          onClick={startNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-orange-700 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-orange-300"
        >
          <MessageSquarePlus size={16} strokeWidth={1.5} />
          {isEn ? 'New chat' : 'แชทใหม่'}
        </button>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => navigate(localePath('/dashboard', routing))}
            className="min-h-9 px-3 rounded-xl border border-slate-200 bg-white/70 text-xs font-medium text-slate-600 hover:border-amber-600/30 hover:text-amber-700 hover:bg-amber-50/50 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300 dark:hover:text-amber-300 transition-all flex items-center justify-center gap-1.5"
          >
            <ArrowLeft size={14} strokeWidth={1.5} />
            {isEn ? 'Overview' : 'ภาพรวม'}
          </button>
          <button
            onClick={() => navigate(buildFilesPath(routing, {}))}
            className="min-h-9 px-3 rounded-xl border border-slate-200 bg-white/70 text-xs font-medium text-slate-600 hover:border-amber-600/30 hover:text-amber-700 hover:bg-amber-50/50 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300 dark:hover:text-amber-300 transition-all flex items-center justify-center gap-1.5"
          >
            <FolderOpen size={14} strokeWidth={1.5} />
            {isEn ? 'Files' : 'ไฟล์ข้อมูล'}
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto no-scrollbar px-3 py-4">
        <div className="mb-3 flex items-center justify-between px-2">
          <h4 className="text-[9px] uppercase tracking-[0.16em] text-slate-400 font-mono font-bold">
            {isEn ? 'Conversations' : 'การสนทนา'}
          </h4>
          <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[9px] font-mono font-semibold text-slate-500 dark:text-slate-400">
            {conversations.length}
          </span>
        </div>
        <div className="space-y-1">
          {conversations.length > 0 ? (
            conversations.map((conv) => {
              const isPinned = pinnedConvIds.includes(conv.id) || conv.is_pinned;
              const isActive = activeConversationId === conv.id;
              return (
                <div key={conv.id} className="relative group mb-1">
                  {editingId === conv.id ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-900 rounded-xl border border-amber-600/30 shadow-sm">
                      <input
                        type="text"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => handleSaveRename(conv.id)}
                        onKeyDown={(e) => handleKeyDown(e, conv.id)}
                        autoFocus
                        className="w-full bg-transparent text-sm focus:outline-none dark:text-slate-100 font-sans py-1"
                      />
                    </div>
                  ) : (
                    <>
                      <button 
                        onClick={() => loadConversation(conv.id)}
                        className={`flex min-h-10 w-full items-center justify-between gap-1.5 truncate rounded-lg border px-3 py-2 pr-10 text-left font-sans text-[13px] transition-colors ${
                          isActive
                            ? 'border-orange-200/80 bg-orange-50/75 font-semibold text-stone-900 dark:border-orange-900/60 dark:bg-orange-950/25 dark:text-stone-100'
                            : 'border-transparent text-stone-500 hover:bg-stone-100/80 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800/70 dark:hover:text-stone-100'
                        }`}
                      >
                        <span className="truncate flex-1">{conv.title}</span>
                        {isPinned && (
                          <Pin size={12} className="text-[#d97706] rotate-45 transform shrink-0" strokeWidth={2.5} />
                        )}
                      </button>
                      
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveDropdownId(activeDropdownId === conv.id ? null : conv.id);
                        }}
                        className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 z-20 transition-colors rounded-lg hover:bg-white dark:hover:bg-slate-800 ${activeDropdownId === conv.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        title={isEn ? 'More actions' : 'ตัวเลือกเพิ่มเติม'}
                      >
                        <MoreVertical size={14} strokeWidth={1.5} />
                      </button>

                      {activeDropdownId === conv.id && (
                        <div 
                          ref={dropdownRef} 
                          className="absolute right-2 top-11 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl py-1.5 z-[100] w-36 overflow-hidden"
                        >
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinConversation(conv.id);
                              setActiveDropdownId(null);
                            }}
                            className="w-full text-left px-3 py-2 text-xs font-sans font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/50 flex items-center gap-2 transition-colors"
                          >
                            <Pin size={13} className="rotate-45" strokeWidth={1.5} />
                            {isPinned ? (isEn ? 'Unpin' : 'ถอนหมุด') : (isEn ? 'Pin' : 'ปักหมุด')}
                          </button>
                          
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleStartRename(conv);
                            }}
                            className="w-full text-left px-3 py-2 text-xs font-sans font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/50 flex items-center gap-2 transition-colors"
                          >
                            <Edit2 size={13} strokeWidth={1.5} />
                            {isEn ? 'Rename' : 'เปลี่ยนชื่อ'}
                          </button>
                          
                          <div className="h-px bg-slate-100 dark:bg-slate-700 my-1" />
                          
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              triggerDeleteConversation(e, conv.id, conv.title);
                              setActiveDropdownId(null);
                            }}
                            className="w-full text-left px-3 py-2 text-xs font-sans font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 flex items-center gap-2 transition-colors"
                          >
                            <Trash2 size={13} strokeWidth={1.5} />
                            {isEn ? 'Delete' : 'ลบแชท'}
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })
          ) : (
            <p className="text-xs text-slate-400 font-sans text-center py-4">{isEn ? 'No chat history' : 'ไม่มีประวัติการแชท'}</p>
          )}
          {hasMoreConversations && (
            <button
              type="button"
              onClick={loadMoreConversations}
              disabled={loadingMoreConversations}
              className="mt-2 w-full rounded-lg px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            >
              {loadingMoreConversations
                ? (isEn ? 'Loading…' : 'กำลังโหลด…')
                : (isEn ? 'Load older conversations' : 'โหลดการสนทนาเก่าเพิ่มเติม')}
            </button>
          )}
        </div>
      </div>

      <div className="p-3 border-t border-slate-200 dark:border-slate-800 shrink-0">
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-3 dark:border-slate-800 dark:bg-slate-900/55">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-9 h-9 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center text-slate-600 dark:text-slate-300 font-semibold text-xs shadow-sm">
            {user?.user_metadata?.avatar_url ? (
              <img src={user.user_metadata.avatar_url} alt="Profile" className="w-full h-full object-cover" />
            ) : (
              userInitial
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate font-sans leading-none mb-1">{user?.user_metadata?.full_name || (isEn ? 'User' : 'ผู้ใช้')}</p>
              <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[8px] font-bold uppercase text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">{plan?.name || 'Free'}</span>
            </div>
            <p className="text-[10px] text-slate-400 truncate font-sans">{user?.email}</p>
          </div>
        </div>

        {renderPlanUsage()}

        <div className="mt-3 px-1 space-y-1 text-[10px] text-slate-400 font-sans">
          {showDailyReset && (
            <div className="flex justify-between gap-2">
              <span>{isEn ? 'Daily reset' : 'รีเซ็ตรายวัน'}</span>
              <span className="font-medium text-slate-500 dark:text-slate-300 tabular-nums">{formatResetLabel(dailyResetAt)}</span>
            </div>
          )}
          {showWeeklyReset && (
            <div className="flex justify-between gap-2">
              <span>{isEn ? 'Weekly reset' : 'รีเซ็ตรายสัปดาห์'}</span>
              <span className="font-medium text-slate-500 dark:text-slate-300 tabular-nums">{formatResetLabel(weeklyResetAt)}</span>
            </div>
          )}
          {timezone && (
            <p className="pt-0.5 truncate" title={timezone}>
              {isEn ? 'Timezone' : 'เขตเวลา'}: {timezone}
            </p>
          )}
        </div>
        </div>
      </div>
    </aside>
  );
};

export default ChatSidebar;
