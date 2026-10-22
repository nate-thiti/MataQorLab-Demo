// @ts-nocheck
import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  BarChart3,
  Braces,
  ChevronDown,
  Database,
  FileArchive,
  FileText,
  FolderOpen,
  Globe,
  Cloud,
  CalendarClock,
  ChartNoAxesCombined,
  Workflow,
  LogOut,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Table,
} from '@/components/icons';
import MQLogo from '../assets/MQ.svg';
import { buildChatPath, buildCustomerCenterPath, buildFilesPath, buildSettingsPath, buildVisualizationPath, isNavActive } from '../utils/dashboardRoutes.js';
import { localePath } from '../utils/locale.js';

const navButtonClass = (active, isOpen) =>
  `w-full h-10 px-3 rounded-lg text-sm font-medium transition-colors flex items-center ${
    isOpen ? 'justify-start gap-3' : 'justify-center'
  } ${
    active
      ? 'sidebar-active text-orange-800 dark:text-orange-200'
      : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 hover:text-slate-800 dark:hover:text-slate-100'
  }`;

const subButtonClass = (active) =>
  `w-full min-h-8 px-3 py-1.5 rounded-lg text-xs transition-colors flex items-center justify-between gap-2 ${
    active
      ? 'bg-orange-50 dark:bg-orange-500/10 text-orange-800 dark:text-orange-200 font-semibold'
      : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 hover:text-slate-800 dark:hover:text-slate-100'
  }`;

const DashboardSidebar = ({
  isOpen,
  setIsOpen,
  user,
  plan,
  routing,
  isEn,
  onLogout,
  fileMenu,
}) => {
  const router = useRouter();
  const pathname = usePathname();
  const [isAccountOpen, setIsAccountOpen] = useState(false);

  const userInitial = user?.email?.charAt(0).toUpperCase() || '?';
  const isActive = (path) => isNavActive(pathname, path, routing.localePrefix);
  const showFileSubmenu = isOpen && (isActive('/files') || fileMenu);

  const navigate = (path) => {
    router.push(path);
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setIsOpen(false);
    }
  };

  const selectFileFilter = (filter) => {
    if (fileMenu?.setFilter) {
      fileMenu.setFilter('files', filter);
      if (typeof window !== 'undefined' && window.innerWidth < 768) setIsOpen(false);
    } else {
      navigate(buildFilesPath(routing, { view: 'files', filter }));
    }
  };

  const selectFileView = (view) => {
    if (fileMenu?.setActiveView) {
      fileMenu.setActiveView(view);
      if (typeof window !== 'undefined' && window.innerWidth < 768) setIsOpen(false);
    } else {
      navigate(buildFilesPath(routing, { view }));
    }
  };

  const navItems = [
    {
      label: isEn ? 'Overview' : 'ภาพรวม',
      path: localePath('/dashboard', routing),
      activePath: '/dashboard',
      Icon: BarChart3,
    },
    {
      label: isEn ? 'Files' : 'ไฟล์ข้อมูล',
      path: buildFilesPath(routing, {}),
      activePath: '/files',
      Icon: FolderOpen,
    },
    {
      label: isEn ? 'Chat' : 'แชท',
      path: buildChatPath(routing, {}),
      activePath: '/chat',
      Icon: MessageSquare,
    },
    {
      label: isEn ? 'Findings' : 'Findings',
      path: buildVisualizationPath(routing),
      activePath: '/visualizations',
      Icon: ChartNoAxesCombined,
    },
    {
      label: isEn ? 'Customer Center' : 'Customer Center',
      path: buildCustomerCenterPath(routing),
      activePath: '/customer-center',
      Icon: Workflow,
    },
    {
      label: isEn ? 'Settings' : 'ตั้งค่า',
      path: buildSettingsPath(routing),
      activePath: '/settings',
      Icon: Settings,
    },
  ];

  const fileSubItems = [
    { key: 'all', label: isEn ? 'All Documents' : 'เอกสารทั้งหมด', Icon: FileText, count: fileMenu?.filesCount },
    { key: 'csv', label: isEn ? 'CSV Files' : 'ไฟล์ CSV', Icon: FileText },
    { key: 'excel', label: isEn ? 'Excel Files' : 'ไฟล์ Excel', Icon: Table },
    { key: 'json', label: isEn ? 'JSON Files' : 'ไฟล์ JSON', Icon: Braces },
    { key: 'parquet', label: isEn ? 'Parquet Files' : 'ไฟล์ PARQUET', Icon: FileArchive },
  ];

  return (
    <>
      <aside
        className={`app-sidebar fixed md:relative inset-y-0 left-0 z-[60] md:z-20 shrink-0 border-r border-slate-200 bg-white shadow-[12px_0_34px_rgba(15,23,42,0.04)] backdrop-blur-lg dark:border-zinc-800 dark:bg-zinc-950 transition-all duration-300 ease-in-out flex flex-col overflow-hidden ${
          isOpen ? 'translate-x-0 w-72' : 'translate-x-0 w-16'
        }`}
      >
        <div className={`h-16 px-3 border-b border-slate-200 dark:border-slate-800 flex items-center ${isOpen ? 'justify-start' : 'justify-center'}`}>
          <button
            onClick={() => setIsOpen((open) => !open)}
            className={`group min-w-0 flex items-center rounded-lg transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 ${
              isOpen ? 'w-full gap-2 p-2' : 'justify-center p-2'
            }`}
            title={isOpen ? (isEn ? 'Collapse sidebar' : 'ย่อเมนู') : (isEn ? 'Expand sidebar' : 'ขยายเมนู')}
          >
            <span className="relative flex w-8 h-8 items-center justify-center shrink-0">
              <img
                src={MQLogo?.src || MQLogo}
                alt="MataQorLab Logo"
                className="absolute inset-0 w-8 h-8 object-contain transition-opacity duration-150 group-hover:opacity-0"
              />
              {isOpen ? (
                <PanelLeftClose className="absolute w-5 h-5 text-slate-500 dark:text-slate-400 opacity-0 transition-opacity duration-150 group-hover:opacity-100" strokeWidth={1.5} />
              ) : (
                <PanelLeftOpen className="absolute w-5 h-5 text-slate-500 dark:text-slate-400 opacity-0 transition-opacity duration-150 group-hover:opacity-100" strokeWidth={1.5} />
              )}
            </span>
            {isOpen && (
              <span className="text-base font-semibold tracking-tight text-slate-800 dark:text-slate-100 truncate">
                MataQorLab
              </span>
            )}
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto no-scrollbar p-3 space-y-1">
          {navItems.map(({ label, path, activePath, Icon }) => {
            const active = isActive(activePath);
            return (
              <div key={activePath}>
                <button
                  onClick={() => navigate(path)}
                  className={navButtonClass(active, isOpen)}
                  title={label}
                >
                  <Icon size={18} className="shrink-0" strokeWidth={1.5} />
                  {isOpen && <span className="truncate">{label}</span>}
                  {isOpen && activePath === '/files' && (
                    <ChevronDown size={14} className={`ml-auto transition-transform ${showFileSubmenu ? 'rotate-0' : '-rotate-90'}`} strokeWidth={1.5} />
                  )}
                </button>

                {activePath === '/files' && showFileSubmenu && (
                  <div className="mt-2 mb-3 ml-4 pl-3 border-l border-slate-200 dark:border-slate-800 space-y-1">
                    <p className="px-3 pt-1 pb-1 text-[10px] uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500 font-semibold">
                      {isEn ? 'Data Files' : 'ไฟล์ข้อมูล'}
                    </p>
                    {fileSubItems.map(({ key, label: subLabel, Icon: SubIcon, count }) => (
                      <button
                        key={key}
                        onClick={() => selectFileFilter(key)}
                        className={subButtonClass((fileMenu?.activeView === 'files' || !fileMenu) && (fileMenu?.filter || 'all') === key)}
                      >
                        <span className="flex items-center gap-2 min-w-0">
                          <SubIcon size={14} className="shrink-0" strokeWidth={1.5} />
                          <span className="truncate">{subLabel}</span>
                        </span>
                        {typeof count === 'number' && <span className="text-[10px] opacity-50">{count}</span>}
                      </button>
                    ))}

                    <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500 font-semibold">
                      {isEn ? 'Connections' : 'การเชื่อมต่อ'}
                    </p>
                    <button
                      onClick={() => selectFileView('cloud')}
                      className={subButtonClass(fileMenu?.activeView === 'cloud')}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Cloud size={14} strokeWidth={1.5} />
                        <span className="truncate">{isEn ? 'Cloud files' : 'ไฟล์ Cloud'}</span>
                      </span>
                    </button>
                    <button
                      onClick={() => selectFileView('sql')}
                      className={subButtonClass(fileMenu?.activeView === 'sql')}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Database size={14} strokeWidth={1.5} />
                        <span className="truncate">{isEn ? 'SQL Databases' : 'ฐานข้อมูล SQL'}</span>
                      </span>
                    </button>
                    <button
                      onClick={() => selectFileView('api')}
                      className={subButtonClass(fileMenu?.activeView === 'api')}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Globe size={14} strokeWidth={1.5} />
                        <span className="truncate">{isEn ? 'REST APIs' : 'เชื่อมต่อ API'}</span>
                      </span>
                    </button>

                    <p className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500 font-semibold">
                      {isEn ? 'Automation' : 'ระบบอัตโนมัติ'}
                    </p>
                    <button
                      onClick={() => selectFileView('schedules')}
                      className={subButtonClass(fileMenu?.activeView === 'schedules')}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <CalendarClock size={14} strokeWidth={1.5} />
                        <span className="truncate">{isEn ? 'Scheduled ETL' : 'ตั้งเวลา ETL'}</span>
                      </span>
                    </button>

                  </div>
                )}

              </div>
            );
          })}
        </nav>

        <div className="p-3 border-t border-slate-200 dark:border-slate-800">
          <button
            onClick={() => setIsAccountOpen((open) => !open)}
            className={`w-full rounded-lg transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60 flex items-center ${isOpen ? 'gap-3 p-2' : 'justify-center p-1.5'}`}
            title={user?.email || 'Account'}
          >
            <div className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-300 font-semibold overflow-hidden shrink-0">
              {user?.user_metadata?.avatar_url ? (
                <img src={user.user_metadata.avatar_url} alt="Profile" className="w-full h-full object-cover" />
              ) : (
                userInitial
              )}
            </div>
            {isOpen && (
              <div className="min-w-0 text-left">
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">
                  {user?.user_metadata?.full_name || (isEn ? 'User' : 'ผู้ใช้งาน')}
                </p>
                <p className="text-[10px] text-slate-400 truncate">{user?.email || 'Loading...'}</p>
              </div>
            )}
          </button>

          {isOpen && isAccountOpen && (
            <div className="mt-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/30 p-2 space-y-1">
              <div className="px-2 py-1.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                {plan?.name || 'Free'} Plan
              </div>
              <button
                onClick={onLogout}
                className="w-full px-2 py-2 rounded-lg text-xs text-left text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors flex items-center gap-2"
                title={isEn ? 'Sign out' : 'ออกจากระบบ'}
              >
                <LogOut size={14} strokeWidth={1.5} />
                {isEn ? 'Sign out' : 'ออกจากระบบ'}
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
};

export default DashboardSidebar;
