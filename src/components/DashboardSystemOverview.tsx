// @ts-nocheck
import { t, getMessages } from '../utils/i18n.js';
import { getProgressFillClass } from '../utils/progressColor.js';
import { Clock3, Database, Link2 } from '@/components/icons';

function StatusDot({ active, isEn, m }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        active
          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
          : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-emerald-600 dark:bg-emerald-400' : 'bg-slate-400'}`} />
      {active ? t(m, 'dashboard.active', 'พร้อมใช้') : (isEn ? 'Idle' : 'ว่าง')}
    </span>
  );
}

const DashboardSystemOverview = ({
  stats,
  plan,
  isEn,
  routing,
  profileUsage = { usedToday: 0, usedWeek: 0, dailyResetAt: null, weeklyResetAt: null, timezone: 'UTC' },
  dbConnections = [],
  apiConnections = [],
  recentFiles = []
}) => {
  const m = getMessages(routing.locale);

  const usedMB = (stats.totalSize / (1024 * 1024)).toFixed(2);
  const planStorageMB = plan.storage_limit_mb || 0;
  const usagePercentage = planStorageMB > 0 ? (parseFloat(usedMB) / planStorageMB) * 100 : 0;
  const remainingMB = Math.max(0, planStorageMB - parseFloat(usedMB)).toFixed(2);

  const objectStorageBytes = stats.storageBytes ?? stats.totalSize;
  const databaseBytes = stats.databaseBytes ?? 0;
  const formatBytes = (bytes) => {
    if (!bytes) return `0 ${t(m, 'file_manager.kb', 'KB')}`;
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const lastUpload = recentFiles.length > 0 ? recentFiles[0] : null;
  const lastUploadTime = lastUpload ? new Date(lastUpload.created_at).toLocaleString(isEn ? 'en-US' : 'th-TH', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }) : t(m, 'dashboard.no_uploads', 'ไม่มีประวัติอัปโหลด');

  const formatResetTime = (dateStr) => {
    if (!dateStr) return t(m, 'dashboard.not_scheduled', 'ไม่มีการบันทึก');
    const date = new Date(dateStr);
    const tz = profileUsage.timezone || undefined;
    return date.toLocaleString(isEn ? 'en-US' : 'th-TH', {
      timeZone: tz,
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  };

  const planNameLower = (plan.name || "Free").toLowerCase();
  const hasProAccess = planNameLower === 'pro' || planNameLower === 'enterprise';
  const progressClass = getProgressFillClass(usagePercentage);

  return (
    <div className="enterprise-panel p-6 space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
          {t(m, 'dashboard.system_overview_title', 'สรุปข้อมูลสถานะระบบ')}
        </h3>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {t(m, 'dashboard.system_overview_desc', 'รายละเอียดการทำงานของเซิร์ฟเวอร์และขีดจำกัด')}
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex justify-between items-end gap-3">
          <div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">
              {t(m, 'dashboard.storage_breakdown', 'พื้นที่จัดเก็บ')}
            </p>
            <p className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white mt-0.5">
              {usedMB} MB <span className="text-slate-400 font-medium">/</span> {planStorageMB} MB
            </p>
          </div>
          <span className="text-xs text-slate-500 dark:text-slate-400 font-medium tabular-nums">
            {usagePercentage.toFixed(1)}% {t(m, 'dashboard.active', 'ใช้ไป')}
          </span>
        </div>
        <div className="progress-track h-2">
          <div className={progressClass} style={{ width: `${Math.min(usagePercentage, 100)}%` }} />
        </div>

        <div className="grid grid-cols-2 gap-3 pt-1">
          <div className="rounded-xl border border-slate-200/70 dark:border-white/10 bg-slate-50/80 dark:bg-zinc-900/50 px-3.5 py-3">
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">
              {t(m, 'dashboard.remaining_space', 'คงเหลือ')}
            </p>
            <p className="font-semibold tabular-nums text-slate-900 dark:text-white text-sm mt-1">{remainingMB} MB</p>
          </div>
          <div className="rounded-xl border border-slate-200/70 dark:border-white/10 bg-slate-50/80 dark:bg-zinc-900/50 px-3.5 py-3">
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">
              {isEn ? 'Files & artifacts' : 'ไฟล์และ Artifact'}
            </p>
            <p className="font-semibold tabular-nums text-slate-900 dark:text-white text-sm mt-1">{formatBytes(objectStorageBytes)}</p>
          </div>
        </div>

        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 pt-1">
          <span>{isEn ? 'Chat & account data' : 'แชทและข้อมูลบัญชี'}</span>
          <span className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{formatBytes(databaseBytes)}</span>
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-200/80 dark:border-white/10">
          <span>{t(m, 'dashboard.last_uploaded', 'อัปโหลดล่าสุด')}</span>
          <span className="font-semibold text-slate-800 dark:text-slate-100">{lastUploadTime}</span>
        </div>
      </div>

      {planNameLower !== 'free' && (
        <div className="space-y-3 pt-4 border-t border-slate-200/80 dark:border-white/10">
          <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">
            {t(m, 'dashboard.integrations_status', 'การเชื่อมต่อคลังข้อมูล')}
          </p>
          <div className={`grid gap-3 ${hasProAccess ? 'grid-cols-2' : 'grid-cols-1'}`}>
            {hasProAccess && (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/70 dark:border-white/10 bg-slate-50/80 dark:bg-zinc-900/50 px-3.5 py-3.5">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white dark:bg-zinc-800 text-[#d97706]">
                    <Database className="h-4 w-4" strokeWidth={1.6} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      {t(m, 'dashboard.sql_dbs', 'ฐานข้อมูล SQL')}
                    </p>
                    <p className="text-base font-semibold tabular-nums text-slate-900 dark:text-white mt-0.5">
                      {dbConnections.length}
                    </p>
                  </div>
                </div>
                <StatusDot active={dbConnections.length > 0} isEn={isEn} m={m} />
              </div>
            )}

            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/70 dark:border-white/10 bg-slate-50/80 dark:bg-zinc-900/50 px-3.5 py-3.5">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white dark:bg-zinc-800 text-[#d97706]">
                  <Link2 className="h-4 w-4" strokeWidth={1.6} />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    {t(m, 'dashboard.rest_apis', 'ตัวเชื่อมต่อ API')}
                  </p>
                  <p className="text-base font-semibold tabular-nums text-slate-900 dark:text-white mt-0.5">
                    {apiConnections.length}
                  </p>
                </div>
              </div>
              <StatusDot active={apiConnections.length > 0} isEn={isEn} m={m} />
            </div>
          </div>
        </div>
      )}

      <div className="space-y-2.5 pt-4 border-t border-slate-200/80 dark:border-white/10">
        <div className="flex items-center gap-2">
          <Clock3 className="h-3.5 w-3.5 text-slate-400" strokeWidth={1.75} />
          <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium uppercase tracking-wider">
            {t(m, 'dashboard.quota_resets_schedule', 'กำหนดเวลารีเซ็ตโควตา')}
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200/70 dark:border-white/10 px-3.5 py-3">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t(m, 'dashboard.next_daily_reset', 'รีเซ็ตโควตารายวันถัดไป')}</p>
            <p className="mt-1 text-xs font-semibold text-slate-900 dark:text-slate-100">{formatResetTime(profileUsage.dailyResetAt)}</p>
          </div>
          <div className="rounded-xl border border-slate-200/70 dark:border-white/10 px-3.5 py-3">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">{t(m, 'dashboard.next_weekly_reset', 'รีเซ็ตโควตารายสัปดาห์ถัดไป')}</p>
            <p className="mt-1 text-xs font-semibold text-slate-900 dark:text-slate-100">{formatResetTime(profileUsage.weeklyResetAt)}</p>
          </div>
        </div>
        {profileUsage.timezone && (
          <p className="text-[11px] text-slate-400">
            {isEn ? 'Timezone' : 'เขตเวลา'}: {profileUsage.timezone}
          </p>
        )}
      </div>
    </div>
  );
};

export default DashboardSystemOverview;
