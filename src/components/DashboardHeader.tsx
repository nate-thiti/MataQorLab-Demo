// @ts-nocheck
import Link from 'next/link';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { getMessages, t } from '../utils/i18n.js';
import { Shield, BarChart3, FolderOpen } from '@/components/icons';

const PLAN_COPY = {
  Enterprise: {
    en: 'Your Enterprise team workspace is ready.',
    th: 'Workspace สำหรับทีม Enterprise พร้อมใช้งานแล้ว',
  },
  Pro: {
    en: 'You are ready for maximum processing power (Pro Plan).',
    th: 'พร้อมสำหรับพลังการประมวลผลระดับสูงสุดแล้ว (Pro Plan)',
  },
  Plus: {
    en: 'Boost your business analytics performance (Plus Plan).',
    th: 'ยกระดับการวิเคราะห์ข้อมูลระดับธุรกิจของคุณ (Plus Plan)',
  },
  Free: {
    en: 'Start analyzing your data today (Free Plan).',
    th: 'เริ่มต้นวิเคราะห์ข้อมูลของคุณวันนี้ (Free Plan)',
  },
};

const DashboardHeader = ({ user, plan, isEn, isStatsLoading, analyzeHref, filesHref }) => {
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);
  const planName = plan?.name || 'Free';
  const planCopy = PLAN_COPY[planName] || PLAN_COPY.Free;
  const firstName = user?.user_metadata?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || '';

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return t(m, 'dashboard.greeting_morning', 'Good morning,');
    if (hour < 18) return t(m, 'dashboard.greeting_afternoon', 'Good afternoon,');
    return t(m, 'dashboard.greeting_evening', 'Good evening,');
  };

  return (
    <header className="app-dashboard-header mb-8 font-sans">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="app-page-kicker mb-3">OPERATING OVERVIEW</div>
          <h1 className="text-2xl md:text-[1.75rem] font-semibold text-slate-900 dark:text-white leading-tight tracking-tight">
            {getGreeting()}{' '}
            {isStatsLoading ? (
              <span className="inline-block w-32 h-7 bg-slate-200/60 dark:bg-slate-800/60 animate-pulse rounded-lg align-middle" />
            ) : (
              <span>{firstName}</span>
            )}
          </h1>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-xl">
            {isStatsLoading ? (
              <span className="inline-block w-72 h-4 bg-slate-200/40 dark:bg-slate-800/40 animate-pulse rounded" />
            ) : (
              isEn ? planCopy.en : planCopy.th
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex items-center rounded-lg border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-zinc-900/70 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
            {planName} {t(m, 'dashboard.plan_active', 'พร้อมทำงาน')}
          </span>
          {filesHref && (
            <Link
              href={filesHref}
              className="inline-flex items-center gap-2 rounded-[0.75rem] border border-slate-200 dark:border-white/12 bg-white/90 dark:bg-zinc-900/80 px-3.5 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-white/20 transition-colors"
            >
              <FolderOpen className="h-4 w-4" strokeWidth={1.75} />
              {t(m, 'dashboard.cta_files', isEn ? 'Manage files' : 'จัดการไฟล์')}
            </Link>
          )}
          {analyzeHref && (
            <Link href={analyzeHref} className="btn-primary inline-flex items-center gap-2 px-4 py-2 text-sm">
              <BarChart3 className="h-4 w-4" strokeWidth={1.75} />
              {t(m, 'dashboard.cta_analyze', isEn ? 'Start analysis' : 'เริ่มวิเคราะห์')}
            </Link>
          )}
        </div>
      </div>

      <div className="trust-banner mt-5">
        <Shield size={14} className="text-slate-500 dark:text-slate-400 shrink-0" />
        <span>
          {isEn
            ? 'Data is encrypted in transit and at rest. Your files are isolated to your account.'
            : 'ข้อมูลถูกเข้ารหัสระหว่างส่งและจัดเก็บ ไฟล์ของคุณแยกอยู่ในบัญชีของคุณเท่านั้น'}
        </span>
      </div>
    </header>
  );
};

export default DashboardHeader;
