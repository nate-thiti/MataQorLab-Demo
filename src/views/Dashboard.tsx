// @ts-nocheck
'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { supabase } from '../utils/supabaseClient.js';
import DashboardSidebar from '../components/DashboardSidebar';
import { useAppSidebar } from '../context/AppSidebarContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import DashboardHeader from '../components/DashboardHeader';
import DashboardSystemOverview from '../components/DashboardSystemOverview';
import { authFetch } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';
import { buildChatPath, buildFilesPath } from '../utils/dashboardRoutes.js';
import { t, getMessages } from '../utils/i18n.js';
import { getProgressFillClass } from '../utils/progressColor.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { applyProfileQuotaReset } from '../utils/profileQuota.js';
import { getBrowserTimezone } from '../utils/timezone.js';
import { getDisplayName, getFileIcon } from '../utils/fileDisplay';
import {
  ArrowRight,
  BarChart3,
  Building2,
  Check,
  Database,
  FileText,
  FolderOpen,
  MessageSquareText,
  PackageOpen,
  Lightbulb,
  TriangleAlert,
} from '@/components/icons';

const Dashboard = () => {
  const router = useRouter();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);
  const [user, setUser] = useState<any>(null);
  const { isOpen: isSidebarOpen, setIsOpen: setIsSidebarOpen } = useAppSidebar();
  const fileManagerCache = useFileManagerCache();
  const [stats, setStats] = useState({ files: 0, conversations: 0, totalSize: 0, dailyUsage: 0 });
  const [plan, setPlan] = useState({ name: 'Free', storage_limit_mb: 1, message_limit: 200000 });
  const [statsError, setStatsError] = useState<any>(null);
  const [isStatsLoading, setIsStatsLoading] = useState(true);
  const [profileUsage, setProfileUsage] = useState({ 
    usedToday: 0, 
    usedWeek: 0,
    dailyResetAt: null,
    weeklyResetAt: null,
    timezone: 'UTC',
  });
  
  const [recentFiles, setRecentFiles] = useState<any[]>([]);
  const [isRecentFilesLoading, setIsRecentFilesLoading] = useState(false);
  const [dbConnections, setDbConnections] = useState<any[]>([]);
  const [apiConnections, setApiConnections] = useState<any[]>([]);

  useEffect(() => {
    const getUserData = async () => {
      const e2eUser = getE2eMockUser();
      if (e2eUser) {
        setUser(e2eUser);
        return;
      }
      const cachedAuth = fileManagerCache.getAuthUser();
      if (cachedAuth?.user) {
        setUser(cachedAuth.user);
        const cachedDashboard = fileManagerCache.getDashboard(cachedAuth.user.id);
        if (cachedAuth.isFresh && cachedDashboard) return;
      }
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        setUser(user);
        fileManagerCache.setAuthUser(user);
        
        try {
          const { data: profileData, error: profileError } = await supabase
            .from('profiles')
            .select(`
              plan_id,
              tokens_used_today,
              tokens_used_this_week,
              daily_reset_at,
              weekly_reset_at,
              timezone,
              plans (
                name,
                storage_limit_mb,
                message_limit
              )
            `)
            .eq('id', user.id)
            .maybeSingle();

          if (profileError) throw profileError;

          if (!profileData) {
            const { data: freePlan } = await supabase.from('plans').select('*').eq('name', 'Free').maybeSingle();
            const defaultProfile = {
              id: user.id,
              full_name: user.user_metadata?.full_name || 'User',
              email: user.email,
              plan_id: freePlan?.id || null,
              subscription_status: 'free',
              timezone: getBrowserTimezone(),
            };
            await supabase.from('profiles').insert([defaultProfile]);
            if (freePlan) setPlan(freePlan);
          } else {
            if (profileData.plans) {
              const planData = Array.isArray(profileData.plans) ? profileData.plans[0] : profileData.plans;
              setPlan(planData);
              fileManagerCache.setDashboard(user.id, { plan: planData });
            }
            const quota = await applyProfileQuotaReset(supabase, user.id, profileData);
            const nextProfileUsage = {
              usedToday: quota.tokensUsedToday,
              usedWeek: quota.tokensUsedThisWeek,
              dailyResetAt: quota.dailyResetAt,
              weeklyResetAt: quota.weeklyResetAt,
              timezone: quota.timezone,
            };
            setProfileUsage(nextProfileUsage);
            fileManagerCache.setDashboard(user.id, { profileUsage: nextProfileUsage });
          }
        } catch (err: any) {
          console.error('Error fetching plan info:', err);
        }
      } else {
        await supabase.auth.signOut();
        router.push(localePath('/login', routing));
      }
    };
    getUserData();
  }, [fileManagerCache, router, routing]);

  const fetchStats = useCallback(async (userId, { showLoading = true } = {}) => {
    if (showLoading) setIsStatsLoading(true);
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/dashboard/stats`, { method: 'GET' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not load dashboard stats');

      const nextStats = {
        files: data.files,
        conversations: data.conversations,
        dailyUsage: data.dailyUsage,
        totalSize: data.totalSize,
        storageBytes: data.storageBytes || 0,
        databaseBytes: data.databaseBytes || 0,
        limitBytes: data.limitBytes || 0,
      };
      setStats(nextStats);
      fileManagerCache.setDashboard(userId, { stats: nextStats });

      const { data: profileData } = await supabase
        .from('profiles')
        .select('tokens_used_today, tokens_used_this_week, daily_reset_at, weekly_reset_at, timezone')
        .eq('id', userId)
        .maybeSingle();

      if (profileData) {
        const quota = await applyProfileQuotaReset(supabase, userId, profileData);
        const nextProfileUsage = {
          usedToday: quota.tokensUsedToday,
          usedWeek: quota.tokensUsedThisWeek,
          dailyResetAt: quota.dailyResetAt,
          weeklyResetAt: quota.weeklyResetAt,
          timezone: quota.timezone,
        };
        setProfileUsage(nextProfileUsage);
        fileManagerCache.setDashboard(userId, { profileUsage: nextProfileUsage });
      }
    } catch (err: any) {
      setStatsError((isEn ? 'Unable to load dashboard stats: ' : 'ไม่สามารถดึงข้อมูลสถิติได้: ') + err.message);
    } finally {
      setIsStatsLoading(false);
    }
  }, [fileManagerCache, isEn]);

  const fetchConnections = useCallback(async (userId) => {
    try {
      const response = await authFetch(`${getPublicApiUrl()}/api/v1/connections`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Could not load connections');
      const nextDb = payload.database_connections || [];
      const nextApi = payload.api_connections || [];
      setDbConnections(nextDb);
      setApiConnections(nextApi);
      fileManagerCache.setDatabaseConnections(userId, { connections: nextDb });
      fileManagerCache.setApiConnections(userId, { connections: nextApi });
      fileManagerCache.setDashboard(userId, { dbConnections: nextDb, apiConnections: nextApi });
    } catch (err: any) {
      console.error('Error fetching connections:', err);
    }
  }, [fileManagerCache]);

  const fetchRecentFiles = useCallback(async (userId, { showLoading = true } = {}) => {
    if (showLoading) setIsRecentFilesLoading(true);
    try {
      const { data, error } = await supabase.storage
        .from('business-data')
        .list(userId, {
          limit: 5,
          offset: 0,
          sortBy: { column: 'created_at', order: 'desc' },
        });

      if (error) throw error;
      const nextFiles = data || [];
      setRecentFiles(nextFiles);
      fileManagerCache.setDashboard(userId, { recentFiles: nextFiles });
    } catch (error: any) {
      console.error('Error fetching recent files:', error.message);
    } finally {
      setIsRecentFilesLoading(false);
    }
  }, [fileManagerCache]);

  useEffect(() => {
    if (!user) return undefined;

    let cancelled = false;
    const cached = fileManagerCache.getDashboard(user.id);
    if (cached) {
      if (cached.stats) setStats(cached.stats);
      if (cached.plan) setPlan(cached.plan);
      if (cached.profileUsage) setProfileUsage(cached.profileUsage);
      if (cached.recentFiles) setRecentFiles(cached.recentFiles);
      if (cached.dbConnections) setDbConnections(cached.dbConnections);
      if (cached.apiConnections) setApiConnections(cached.apiConnections);
      setIsStatsLoading(false);
      setIsRecentFilesLoading(false);
      if (cached.isFresh) {
        return () => {
          cancelled = true;
        };
      }
    }

    void (async () => {
      await fetchStats(user.id, { showLoading: !cached });
      if (cancelled) return;
      await fetchConnections(user.id);
      if (cancelled) return;
      await fetchRecentFiles(user.id, { showLoading: !cached });
    })();

    return () => {
      cancelled = true;
    };
  }, [user, fetchStats, fetchConnections, fetchRecentFiles, fileManagerCache]);

  const handleLogout = async () => {
    if (user?.id) fileManagerCache.clearUser(user.id);
    fileManagerCache.clearAuthUser();
    await supabase.auth.signOut();
    router.replace(localePath('/login', routing));
  };

  const formatBytes = (bytes) => {
    if (!bytes) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handlePresetClick = (query) => {
    router.push(buildChatPath(routing, { preset: query }));
  };

  const handleFileChatClick = (file) => {
    router.push(buildChatPath(routing, { fileName: file.name }));
  };

  const usedMB = (stats.totalSize / (1024 * 1024)).toFixed(2);
  const planStorageMB = plan.storage_limit_mb || 0;
  const storagePercentage = planStorageMB > 0 ? (parseFloat(usedMB) / planStorageMB) * 100 : 0;

  const planNameLower = (plan.name || "Free").toLowerCase();
  const isEnterprise = planNameLower.includes("enterprise");
  const isProAccess = planNameLower.includes("pro") || isEnterprise;
  const isDailyLimit = planNameLower.includes("plus") || isProAccess;
  const actualUsage = isDailyLimit ? profileUsage.usedToday : profileUsage.usedWeek;
  const messagesPercentage = plan.message_limit > 0 ? (actualUsage / plan.message_limit) * 100 : 0;
  const quotaProgressClass = getProgressFillClass(messagesPercentage);
  const storageProgressClass = getProgressFillClass(storagePercentage);
  const chatHref = buildChatPath(routing, {});
  const filesHref = buildFilesPath(routing, {});
  const insightPresets = [
    {
      Icon: BarChart3,
      title: isEn ? 'Analyze Sales Growth' : 'วิเคราะห์ยอดขายและอัตราเติบโต',
      desc: isEn ? 'Calculate revenue growth and gross margins.' : 'คำนวณอัตราการเติบโตและ GP Margin ประจำงวด',
      query: isEn ? 'Calculate my sales monthly growth rate and identify peak period.' : 'ช่วยวิเคราะห์อัตราการเติบโตของยอดขายรายเดือนและระบุช่วงเวลาที่มียอดขายสูงสุด'
    },
    {
      Icon: PackageOpen,
      title: isEn ? 'Detect Inventory Deadstock' : 'ค้นหาสินค้าค้างคลัง (Deadstock)',
      desc: isEn ? 'Identify slow-moving items in stock.' : 'วิเคราะห์สินค้าหมุนเวียนช้าและสต็อกค้างเกินกำหนด',
      query: isEn ? 'Check for deadstock and calculate inventory turnover ratios.' : 'ช่วยตรวจสอบหาสินค้าค้างคลัง (Deadstock) และคำนวณอัตราหมุนเวียนสินค้า'
    },
    {
      Icon: Building2,
      title: isEn ? 'Compare Branch Performance' : 'เปรียบเทียบผลงานรายสาขา',
      desc: isEn ? 'Benchmark branches against local average.' : 'เปรียบเทียบลำดับสาขาและผลสัมฤทธิ์รายภาค',
      query: isEn ? 'Compare sales and branch performance indicators.' : 'เปรียบเทียบประสิทธิภาพการขายและวิเคราะห์สาขาที่เป็น Top Performer'
    },
    {
      Icon: TriangleAlert,
      title: isEn ? 'Financial Anomaly Audit' : 'ตรวจจับความผิดปกติทางบัญชี',
      desc: isEn ? 'Audit transactions for margin variances.' : 'วิเคราะห์ค่าเบี่ยงเบนและธุรกรรมที่มีนัยสำคัญ',
      query: isEn ? 'Scan the transactions for mathematical margins anomalies.' : 'ช่วยตรวจหาความผิดปกติ (Anomaly Detection) ของสถิติการเงินหรือยอดขาย'
    }
  ];
  const planFeatures = isEnterprise
    ? [
        t(m, 'landing.pricing_features.enterprise.tokens', '2,000,000 โทเคน (รีเฟรชทุกวัน)'),
        t(m, 'landing.pricing_features.enterprise.reasoning', 'ความสามารถในการวิเคราะห์ที่ซับซ้อนที่สุด'),
        t(m, 'landing.pricing_features.enterprise.upload', 'พื้นที่อัปโหลด 2GB'),
        t(m, 'landing.pricing_features.enterprise.formats', 'รองรับ Format และ Connector ทั้งหมด'),
        t(m, 'landing.pricing_features.enterprise.sso', 'Organization Workspace และ Governed Memory'),
        t(m, 'landing.pricing_features.enterprise.support', 'Priority Support'),
      ]
    : isProAccess
      ? [
          t(m, 'landing.pricing_features.pro.tokens', '1,000,000 โทเคน (รีเฟรชทุกวัน)'),
          t(m, 'landing.pricing_features.pro.weekly_limit', 'ไม่มีขีดจำกัดรายสัปดาห์'),
          t(m, 'landing.pricing_features.pro.web_search', 'ค้นหาหน้าเว็บอัตโนมัติ'),
          t(m, 'landing.pricing_features.pro.reasoning', 'ความสามารถในการวิเคราะห์ที่ซับซ้อนที่สุด'),
          t(m, 'landing.pricing_features.pro.upload', 'พื้นที่อัปโหลด 500MB'),
          t(m, 'landing.pricing_features.pro.formats', 'วิเคราะห์ Excel, CSV, JSON, PARQUET'),
          t(m, 'landing.pricing_features.pro.conapi', 'เชื่อมต่อ API ภายนอก'),
          t(m, 'landing.pricing_features.pro.conn', 'เชื่อมต่อฐานข้อมูล SQL Server'),
        ]
      : planNameLower === 'plus'
        ? [
            t(m, 'landing.pricing_features.plus.tokens', '400,000 โทเคน (รีเฟรชทุกวัน)'),
            t(m, 'landing.pricing_features.plus.web_search', 'ค้นหาหน้าเว็บอัตโนมัติ'),
            t(m, 'landing.pricing_features.plus.reasoning', 'ความสามารถในการวิเคราะห์ที่ซับซ้อนขึ้น'),
            t(m, 'landing.pricing_features.plus.upload', 'พื้นที่อัปโหลด 200MB'),
            t(m, 'landing.pricing_features.plus.formats', 'วิเคราะห์ Excel, CSV, JSON, PARQUET'),
            t(m, 'landing.pricing_features.plus.conn', 'เชื่อมต่อ API ภายนอก'),
          ]
        : [
            t(m, 'landing.pricing_features.free.tokens', '200,000 โทเคน (รีเฟรชทุก 7 วัน)'),
            t(m, 'landing.pricing_features.free.reasoning', 'ความสามารถในการวิเคราะห์ขั้นพื้นฐาน'),
            t(m, 'landing.pricing_features.free.upload', 'พื้นที่อัปโหลด 1MB'),
            t(m, 'landing.pricing_features.free.formats', 'วิเคราะห์ Excel, CSV, JSON'),
          ];

  return (
    <div className="app-shell icon-motion-scope relative flex h-[100svh] overflow-hidden bg-slate-50 text-slate-700 dark:bg-zinc-950 dark:text-zinc-300 font-sans transition-colors duration-300">
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/20 dark:bg-black/60 backdrop-blur-sm z-50 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <DashboardSidebar
        isOpen={isSidebarOpen}
        setIsOpen={setIsSidebarOpen}
        user={user}
        plan={plan}
        routing={routing}
        isEn={isEn}
        onLogout={handleLogout}
      />

      <main className="app-main-scroll min-w-0 flex-1 overflow-y-auto p-5 md:p-8">
        <div className="app-page-frame mx-auto w-full max-w-[1180px]">
        <DashboardHeader
          user={user}
          plan={plan}
          isEn={isEn}
          isStatsLoading={isStatsLoading}
          analyzeHref={chatHref}
          filesHref={filesHref}
        />

        {statsError && (
          <div className="p-4 mb-6 rounded-xl text-sm bg-red-50 border border-red-200 text-red-600 dark:bg-red-950/20 dark:border-red-900/30 dark:text-red-400">
            {statsError}
          </div>
        )}

        <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="enterprise-panel p-5 flex flex-col justify-between min-h-[168px]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  {t(m, 'dashboard.total_datasets', isEn ? 'Total Datasets' : 'คลังไฟล์ข้อมูล')}
                </p>
                <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight text-slate-900 dark:text-white">
                  {isStatsLoading ? '—' : stats.files}
                </p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                <FileText className="h-5 w-5" strokeWidth={1.6} />
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-slate-200/80 dark:border-white/10 flex justify-between items-center text-xs">
              <span className="text-slate-500 dark:text-slate-400">
                {isStatsLoading ? '—' : (stats.conversations || 0)} {t(m, 'dashboard.conversations', isEn ? 'Conversations' : 'บทสนทนา')}
              </span>
              <Link href={chatHref} className="inline-flex items-center gap-1 font-semibold text-[#d97706] hover:underline">
                {isEn ? 'Analyze' : 'วิเคราะห์'} <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
              </Link>
            </div>
          </div>

          <div className="enterprise-panel p-5 flex flex-col justify-between min-h-[168px]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  {t(m, 'dashboard.token_quota', isEn ? 'Processing quota' : 'โควตาประมวลผล')}
                </p>
                <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-slate-900 dark:text-white whitespace-nowrap">
                  {isStatsLoading ? '—' : `${actualUsage.toLocaleString()} / ${plan.message_limit.toLocaleString()}`}
                </p>
              </div>
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-slate-300">
                <MessageSquareText className="h-5 w-5" strokeWidth={1.6} />
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-slate-200/80 dark:border-white/10">
              <div className="progress-track h-1.5 mb-2">
                <div className={quotaProgressClass} style={{ width: `${Math.min(messagesPercentage, 100)}%` }} />
              </div>
              <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 font-medium">
                <span>{isDailyLimit ? (isEn ? 'Daily consumption' : 'อัตราการใช้งานประจำวัน') : (isEn ? 'Weekly consumption' : 'อัตราการใช้งานรายสัปดาห์')}</span>
                <span className="tabular-nums">{messagesPercentage.toFixed(1)}%</span>
              </div>
            </div>
          </div>

          <div className="enterprise-panel p-5 flex flex-col justify-between min-h-[168px]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  {t(m, 'dashboard.storage_allocation', isEn ? 'Storage Allocation' : 'พื้นที่จัดเก็บข้อมูล')}
                </p>
                <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-slate-900 dark:text-white whitespace-nowrap">
                  {isStatsLoading ? '—' : `${usedMB} / ${planStorageMB} MB`}
                </p>
              </div>
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-slate-300">
                <Database className="h-5 w-5" strokeWidth={1.6} />
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-slate-200/80 dark:border-white/10">
              <div className="progress-track h-1.5 mb-2">
                <div className={storageProgressClass} style={{ width: `${Math.min(storagePercentage, 100)}%` }} />
              </div>
              <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 font-medium">
                <span>{plan.name} {isEn ? 'limit' : 'ลิมิต'}</span>
                <span className="tabular-nums">{storagePercentage.toFixed(1)}% {isEn ? 'used' : 'ใช้งานแล้ว'}</span>
              </div>
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="enterprise-panel p-6">
              <div className="flex justify-between items-center gap-3 mb-5">
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(m, 'dashboard.recent_files', isEn ? 'Recent Uploaded Datasets' : 'ไฟล์ข้อมูลอัปโหลดล่าสุด')}
                </h2>
                <Link href={filesHref} className="inline-flex items-center gap-1 text-xs font-semibold text-[#d97706] hover:underline">
                  {t(m, 'dashboard.view_files', isEn ? 'View all files' : 'ดูไฟล์ทั้งหมด')}
                  <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
                </Link>
              </div>

              {isRecentFilesLoading ? (
                <div className="space-y-3">
                  <div className="h-14 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded-xl" />
                  <div className="h-14 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded-xl" />
                  <div className="h-14 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded-xl" />
                </div>
              ) : recentFiles.length === 0 ? (
                <div className="flex flex-col items-center justify-center text-center py-10 px-4 rounded-xl border border-dashed border-slate-200 dark:border-white/12 bg-slate-50/70 dark:bg-zinc-900/40">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white dark:bg-zinc-800 text-[#d97706] mb-3">
                    <FolderOpen className="h-5 w-5" strokeWidth={1.6} />
                  </div>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {t(m, 'dashboard.empty_files_title', isEn ? 'No datasets uploaded yet.' : 'ยังไม่มีไฟล์อัปโหลดในระบบ')}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-sm">
                    {t(m, 'dashboard.empty_files_desc', isEn ? 'Upload CSV, Excel, or JSON to start analyzing.' : 'อัปโหลด CSV, Excel หรือ JSON เพื่อเริ่มวิเคราะห์')}
                  </p>
                  <Link href={filesHref} className="btn-primary mt-4 inline-flex items-center px-4 py-2 text-sm">
                    {t(m, 'dashboard.cta_files', isEn ? 'Manage files' : 'จัดการไฟล์')}
                  </Link>
                </div>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-white/10">
                  {recentFiles.map((file, idx) => {
                    const fileInfo = getFileIcon(file.name);
                    const displayName = getDisplayName(file.name);
                    return (
                      <li key={file.id || idx} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                        <div className={`h-10 w-10 shrink-0 rounded-lg flex items-center justify-center ${fileInfo.bgColor} ${fileInfo.textColor}`}>
                          {fileInfo.icon}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate" title={file.name}>
                            {displayName}
                          </p>
                          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                            {formatBytes(file.metadata?.size)} · {new Date(file.created_at).toLocaleDateString(isEn ? 'en-US' : 'th-TH', { month: 'short', day: 'numeric', year: 'numeric' })} · {isEn ? 'Upload' : 'อัปโหลด'}
                          </p>
                        </div>
                        <button
                          onClick={() => handleFileChatClick(file)}
                          className="shrink-0 px-3 py-1.5 border border-slate-200 dark:border-white/12 text-slate-700 dark:text-slate-200 font-medium rounded-lg hover:bg-slate-50 dark:hover:bg-zinc-800 transition-colors text-xs"
                        >
                          {t(m, 'dashboard.chat_analyze', isEn ? 'Chat' : 'แชทวิเคราะห์')}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <DashboardSystemOverview
              stats={stats}
              plan={plan}
              isEn={isEn}
              routing={routing}
              profileUsage={profileUsage}
              dbConnections={dbConnections}
              apiConnections={apiConnections}
              recentFiles={recentFiles}
            />
          </div>

          <div className="space-y-6">
            <div className="enterprise-panel p-6">
              <div className="flex items-center gap-2 mb-5">
                <Lightbulb className="h-4 w-4 text-[#d97706]" strokeWidth={1.75} />
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(m, 'dashboard.quick_insights', isEn ? 'Quick insights' : 'เริ่มวิเคราะห์ด่วน')}
                </h2>
              </div>
              <div className="space-y-2">
                {insightPresets.map((item) => (
                  <button
                    key={item.title}
                    onClick={() => handlePresetClick(item.query)}
                    className="w-full text-left p-3 rounded-xl border border-slate-200/70 dark:border-white/10 bg-slate-50/80 dark:bg-zinc-900/45 hover:border-amber-300/70 dark:hover:border-amber-500/30 hover:bg-amber-50/50 dark:hover:bg-amber-500/5 transition-colors flex items-start gap-3"
                  >
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white dark:bg-zinc-800 text-[#d97706]">
                      <item.Icon className="h-4 w-4" strokeWidth={1.6} />
                    </div>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold text-slate-900 dark:text-white">{item.title}</span>
                      <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{item.desc}</span>
                    </span>
                    <ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-slate-400" strokeWidth={2} />
                  </button>
                ))}
              </div>
            </div>

            <div className="enterprise-panel p-6 space-y-4">
              <div className="flex justify-between items-center gap-3">
                <span className="font-semibold text-slate-800 dark:text-slate-200 uppercase tracking-wider text-xs">
                  {plan.name} {t(m, 'dashboard.plan_active', 'พร้อมทำงาน')}
                </span>
                {!isProAccess && (
                  <button
                    onClick={() => router.push(localePath('/pricing', routing))}
                    className="text-xs btn-primary px-3 py-1.5 font-semibold"
                  >
                    {t(m, 'dashboard.upgrade', 'อัปเกรด')}
                  </button>
                )}
              </div>
              <ul className="space-y-2.5">
                {planFeatures.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#d97706]" strokeWidth={2.2} />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
