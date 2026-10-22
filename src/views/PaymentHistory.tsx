// @ts-nocheck
'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { supabase } from '../utils/supabaseClient.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';
import { buildPaymentHistoryPath, buildSettingsPath, isUuid } from '../utils/dashboardRoutes.js';
import { Calendar, CheckCircle2, ArrowLeft, CreditCard, Shield } from '@/components/icons';
import DashboardSidebar from '../components/DashboardSidebar';
import { useAppSidebar } from '../context/AppSidebarContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { getE2eMockUser } from '../utils/e2eAuth.js';

const PaymentHistory = () => {
  const router = useRouter();
  const { paymentId } = useParams();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const { isOpen: isSidebarOpen, setIsOpen: setIsSidebarOpen } = useAppSidebar();
  const fileManagerCache = useFileManagerCache();
  const highlightedRowRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [payments, setPayments] = useState<any[]>([]);
  const [error, setError] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [plan, setPlan] = useState({ name: 'Free', storage_limit_mb: 1, message_limit: 200000 });

  useEffect(() => {
    const fetchPaymentHistory = async () => {
      try {
        const e2eUser = getE2eMockUser();
        if (e2eUser) {
          setUser(e2eUser);
          setLoading(false);
          return;
        }
        const cachedAuth = fileManagerCache.getAuthUser();
        if (cachedAuth?.user) {
          setUser(cachedAuth.user);
          const cached = fileManagerCache.getPaymentHistory(cachedAuth.user.id);
          if (cached) {
            if (cached.plan) setPlan(cached.plan);
            if (cached.payments) setPayments(cached.payments);
            setLoading(false);
            if (cachedAuth.isFresh && cached.isFresh) return;
          }
        }
        const { data: { user: authUser } } = await supabase.auth.getUser();
        if (!authUser) {
          router.push(localePath('/login', routing));
          return;
        }
        setUser(authUser);
        fileManagerCache.setAuthUser(authUser);

        const cached = fileManagerCache.getPaymentHistory(authUser.id);
        if (cached) {
          if (cached.plan) setPlan(cached.plan);
          if (cached.payments) setPayments(cached.payments);
          setLoading(false);
          if (cached.isFresh) return;
        }

        const { data: profileData } = await supabase
          .from('profiles')
          .select(`plans ( name, storage_limit_mb, message_limit )`)
          .eq('id', authUser.id)
          .maybeSingle();

        if (profileData?.plans) {
          const planData = Array.isArray(profileData.plans) ? profileData.plans[0] : profileData.plans;
          setPlan(planData);
          fileManagerCache.setPaymentHistory(authUser.id, { plan: planData });
        }

        const { data, error: fetchError } = await supabase
          .from('payment_history')
          .select('*')
          .order('created_at', { ascending: false });

        if (fetchError) throw fetchError;
        const nextPayments = data || [];
        setPayments(nextPayments);
        fileManagerCache.setPaymentHistory(authUser.id, { payments: nextPayments });
      } catch (err: any) {
        console.error('Error fetching payment history:', err);
        setError(isEn ? 'Unable to load payment history' : 'ไม่สามารถดึงข้อมูลประวัติการชำระเงินได้');
      } finally {
        setLoading(false);
      }
    };

    fetchPaymentHistory();
  }, [fileManagerCache, router, routing, isEn]);

  useEffect(() => {
    if (!paymentId) return;
    if (!isUuid(paymentId)) {
      router.replace(buildPaymentHistoryPath(routing));
    }
  }, [paymentId, router, routing]);

  useEffect(() => {
    if (!paymentId || loading || payments.length === 0) return;
    if (!payments.some((p) => p.id === paymentId)) {
      router.replace(buildPaymentHistoryPath(routing));
      return;
    }
    highlightedRowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [paymentId, loading, payments, router, routing]);

  const handleLogout = async () => {
    if (user?.id) fileManagerCache.clearUser(user.id);
    fileManagerCache.clearAuthUser();
    await supabase.auth.signOut();
    router.replace(localePath('/login', routing));
  };

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
        <button
          onClick={() => router.push(buildSettingsPath(routing, 'plan'))}
          className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100 transition-colors mb-6"
        >
          <ArrowLeft size={16} strokeWidth={1.75} />
          {isEn ? 'Back to Settings' : 'กลับไปหน้าตั้งค่า'}
        </button>

        <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="app-page-kicker mb-3">BILLING CONTROL</div>
            <h1 className="text-xl font-semibold text-slate-900 dark:text-white tracking-tight">
              {isEn ? 'Billing History' : 'ประวัติการชำระเงิน'}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {isEn ? 'Manage subscriptions and view past payment invoices' : 'จัดการการสมัครสมาชิกและดูประวัติใบเสร็จรับเงินย้อนหลัง'}
            </p>
            {user?.email && (
              <p className="mt-2 text-xs text-slate-400">
                {isEn ? 'Billing email' : 'อีเมลเรียกเก็บเงิน'}: {user.email}
              </p>
            )}
          </div>
          {!loading && (
            <span className="inline-flex self-start items-center rounded-lg border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-zinc-900/70 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
              {payments.length} {isEn ? 'invoices' : 'ใบเสร็จ'}
            </span>
          )}
        </header>

        {error && (
          <div className="p-4 mb-6 rounded-xl text-sm bg-red-50 border border-red-200 text-red-600 dark:bg-red-950/20 dark:border-red-900/30 dark:text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <div className="enterprise-panel overflow-hidden">
            <div className="divide-y divide-slate-100 dark:divide-white/10">
              {[0, 1, 2, 3].map((key) => (
                <div key={key} className="flex items-center gap-3 px-4 py-4">
                  <div className="h-10 w-10 rounded-lg bg-slate-100 dark:bg-zinc-800 animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3.5 w-1/3 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded" />
                    <div className="h-3 w-1/4 bg-slate-100 dark:bg-zinc-800 animate-pulse rounded" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : payments.length === 0 ? (
          <div className="enterprise-panel flex flex-col items-center justify-center text-center py-16 px-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-50 dark:bg-amber-500/10 text-[#d97706] mb-4">
              <CreditCard className="h-6 w-6" strokeWidth={1.6} />
            </div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
              {isEn ? 'No invoice history' : 'ไม่มีประวัติการชำระเงิน'}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 max-w-sm">
              {isEn ? 'You do not have any invoices under this account.' : 'คุณยังไม่มีประวัติใบเสร็จชำระเงินในบัญชีนี้'}
            </p>
          </div>
        ) : (
          <div className="enterprise-panel overflow-hidden">
            <div className="hidden md:grid grid-cols-[1.2fr_1fr_1.2fr_0.9fr_0.8fr] gap-3 px-4 py-3 border-b border-slate-200/80 dark:border-white/10 text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <span>{isEn ? 'Plan' : 'แผนสมาชิก'}</span>
              <span>{isEn ? 'Invoice ID' : 'รหัสใบเสร็จ'}</span>
              <span>{isEn ? 'Date' : 'วันที่ชำระ'}</span>
              <span>{isEn ? 'Amount' : 'จำนวนเงิน'}</span>
              <span>{isEn ? 'Status' : 'สถานะ'}</span>
            </div>
            <div className="divide-y divide-slate-100 dark:divide-white/10">
              {payments.map((payment) => {
                const isHighlighted = paymentId === payment.id;
                const invoiceId = payment.stripe_invoice_id
                  ? `${payment.stripe_invoice_id.substring(0, 15)}...`
                  : 'N/A';
                return (
                  <div
                    key={payment.id}
                    ref={isHighlighted ? highlightedRowRef : undefined}
                    className={`grid grid-cols-1 md:grid-cols-[1.2fr_1fr_1.2fr_0.9fr_0.8fr] gap-2 md:gap-3 items-center px-4 py-3.5 transition-colors ${
                      isHighlighted
                        ? 'bg-amber-50 dark:bg-amber-500/10'
                        : 'hover:bg-slate-50/80 dark:hover:bg-zinc-800/40'
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">
                        {payment.plan_name || 'Plus'}
                      </p>
                      {(payment.seat_count || 1) > 1 && (
                        <p className="mt-0.5 text-xs text-slate-500">
                          {payment.seat_count} {isEn ? 'users' : 'ผู้ใช้'}
                        </p>
                      )}
                    </div>
                    <p className="text-xs font-mono text-slate-500 dark:text-slate-400 truncate" title={payment.stripe_invoice_id || 'N/A'}>
                      {invoiceId}
                    </p>
                    <p className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
                      <Calendar size={14} strokeWidth={1.6} className="shrink-0 text-slate-400" />
                      {new Date(payment.created_at).toLocaleDateString(isEn ? 'en-US' : 'th-TH', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </p>
                    <p className="text-sm font-semibold tabular-nums text-slate-900 dark:text-white">
                      {Number(payment.amount_paid || 0).toLocaleString()} {payment.currency}
                    </p>
                    <span className="inline-flex w-fit items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300 px-2.5 py-0.5 text-[11px] font-semibold">
                      <CheckCircle2 size={12} />
                      {isEn ? 'Success' : 'สำเร็จ'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="trust-banner mt-8">
          <Shield size={14} className="text-slate-500 dark:text-slate-400 shrink-0" />
          <span>
            {isEn
              ? 'Payments are processed securely via Stripe. Invoice records are retained for billing compliance.'
              : 'การชำระเงินดำเนินการอย่างปลอดภัยผ่าน Stripe ระบบเก็บประวัติใบเสร็จเพื่อการเรียกเก็บเงิน'}
          </span>
        </div>
      </div>
      </main>
    </div>
  );
};

export default PaymentHistory;
