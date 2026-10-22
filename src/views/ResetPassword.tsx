// @ts-nocheck
'use client';

import { useState, useEffect } from 'react';
import { supabase } from '../utils/supabaseClient.js';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff, KeyRound, ShieldCheck } from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import AppBanner from '../components/AppBanner';
import MQLogo from '../assets/MQ.svg';

const ResetPassword = () => {
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const router = useRouter();
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);

  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (!success) return undefined;
    const timer = setTimeout(() => {
      router.push(localePath('/login', routing));
    }, 2000);
    return () => clearTimeout(timer);
  }, [success, router, routing]);

  const handleReset = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    const { error } = await supabase.auth.updateUser({ password });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      setSuccess(t(m, 'reset_password.success', 'Password changed successfully. Please sign in with your new password.'));
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell font-sans flex items-center justify-center p-6 text-slate-900 dark:text-slate-100">
      <div className="enterprise-panel p-8 md:p-10 w-full max-w-md">
        <div className="text-center mb-8 pb-6 border-b border-slate-200 dark:border-slate-700">
          <div className="w-12 h-12 mx-auto mb-5 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200/70 dark:border-amber-800/30 grid place-items-center">
            <img src={MQLogo?.src || MQLogo} alt="MataQorLab" className="w-8 h-8" />
          </div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t(m, 'reset_password.title', 'Set New Password')}</h1>
          <p className="text-slate-600 dark:text-slate-400 mt-2 text-sm">{t(m, 'reset_password.subtitle', 'Please enter your new password.')}</p>
        </div>

        {error && <AppBanner type="error" message={error} />}

        {success && <AppBanner type="success" message={success} />}

        <form onSubmit={handleReset} className="space-y-6">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">
              {t(m, 'reset_password.password', 'New password')}
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t(m, 'reset_password.password_placeholder', 'At least 6 characters')}
                className="block w-full p-3 pr-11 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 dark:text-slate-100 focus:border-[#d97706] focus:ring-1 focus:ring-[#d97706] focus:outline-none text-sm transition-colors placeholder-slate-400 dark:placeholder-slate-400"
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={t(
                  m,
                  showPassword ? 'reset_password.hide_password' : 'reset_password.show_password',
                  showPassword ? 'Hide password' : 'Show password',
                )}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 btn-primary text-sm flex items-center justify-center disabled:opacity-50"
          >
            {loading ? t(m, 'reset_password.saving', 'Saving...') : t(m, 'reset_password.save', 'Save new password')}
          </button>
        </form>
      </div>

      <div className="auth-system-visual" aria-hidden="true">
        <div className="auth-visual-core">
          <div className="auth-visual-card text-center">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-600 text-white grid place-items-center shadow-lg shadow-amber-600/20"><KeyRound size={25} /></div>
            <strong className="block mt-5 text-sm">{t(m, 'reset_password.security_title', 'Secure credential update')}</strong>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{t(m, 'reset_password.security_desc', 'Your new credential is protected by encrypted transport and account-level isolation.')}</p>
            <div className="mt-5 inline-flex items-center gap-2 text-[10px] font-bold text-emerald-600"><ShieldCheck size={15} /> {t(m, 'reset_password.security_status', 'SECURE SESSION ACTIVE')}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
