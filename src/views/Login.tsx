// @ts-nocheck
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { Lock, Loader2, Eye, EyeOff } from '@/components/icons';
import api from '../utils/api.js';
import { recoverInvalidBrowserSession, supabase } from '../utils/supabaseClient.js';
import { getBrowserTimezone } from '../utils/timezone.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { absoluteLocaleUrl, localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import { markResetPasswordSent } from '../utils/randomId.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { buildLoginPath, buildRegisterPath, normalizeAppPath, sanitizeRedirectPath } from '../utils/dashboardRoutes.js';
import MQLogo from '../assets/MQ.svg';

const inputClass =
  'app-input block w-full pl-11 pr-4 py-3 text-sm';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<any>(null);
  const [countdown, setCountdown] = useState(() => {
    if (typeof window === 'undefined') return 0;
    const lastSent = localStorage.getItem('last_reset_password_sent');
    if (lastSent) {
      const diff = Math.floor((Date.now() - parseInt(lastSent, 10)) / 1000);
      if (diff < 60) return 60 - diff;
    }
    return 0;
  });
  const [forgotPasswordMode, setForgotPasswordMode] = useState(false);
  const [successMessage, setSuccessMessage] = useState<any>(null);
  const [showPassword, setShowPassword] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const routing = useLocaleRouting();
  const isForgotRoute = normalizeAppPath(pathname, routing.localePrefix) === '/login/forgot';
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);
  const dashboardPath = localePath('/dashboard', routing);

  useEffect(() => {
    let cancelled = false;

    const redirectIfAuthenticated = async () => {
      if (getE2eMockUser()) {
        window.location.replace(dashboardPath);
        return;
      }

      const {
        data: { user },
        error,
      } = await supabase.auth.getUser();
      if (await recoverInvalidBrowserSession(error) || cancelled) return;

      if (user) {
        window.location.replace(dashboardPath);
      }
    };

    const handlePageShow = () => {
      void redirectIfAuthenticated();
    };

    void redirectIfAuthenticated();
    window.addEventListener('pageshow', handlePageShow);

    return () => {
      cancelled = true;
      window.removeEventListener('pageshow', handlePageShow);
    };
  }, [dashboardPath]);

  useEffect(() => {
    setForgotPasswordMode(isForgotRoute);
  }, [isForgotRoute]);

  useEffect(() => {
    let timer;
    if (countdown > 0) {
      timer = setInterval(() => setCountdown(prev => prev - 1), 1000);
    }
    return () => clearInterval(timer);
  }, [countdown]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const { data: { user }, error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) throw authError;

      if (user) {
        await supabase
          .from('profiles')
          .update({ timezone: getBrowserTimezone() })
          .eq('id', user.id);
      }

      await api.post('/auth/login-event', { last_login: new Date().toISOString() }).catch(() => {});

      const redirect = sanitizeRedirectPath(searchParams.get('redirect'));
      window.location.replace(redirect ? localePath(redirect, routing) : dashboardPath);
    } catch (err: any) {
      setError(err.message || t(m, 'login.invalid'));
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    if (countdown > 0) return;

    if (!email) {
      setError(t(m, 'login.need_email'));
      return;
    }
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: absoluteLocaleUrl(window.location.origin, '/reset-password', routing),
      });
      if (error) throw error;

      setSuccessMessage(t(m, 'login.reset_sent'));
      markResetPasswordSent();
      setCountdown(60);
    } catch (err: any) {
      if (err.status === 429 || err.message?.includes('rate limit')) {
        setError(t(m, 'login.rate_limit'));
      } else {
        setError(err.message || t(m, 'login.send_fail'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell auth-shell-centered flex flex-col justify-center py-12 px-6 lg:px-8 font-sans text-slate-900 dark:text-slate-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center mb-6">
          <div className="w-14 h-14 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg flex items-center justify-center">
            <img src={MQLogo?.src || MQLogo} alt="MataQorLab Logo" className="w-10 h-10 object-contain" />
          </div>
        </div>
        <h2 className="text-center text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
          {forgotPasswordMode ? t(m, 'login.forgot_title') : t(m, 'login.welcome')}
        </h2>
        <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-400">
          {forgotPasswordMode ? t(m, 'login.forgot_desc') : t(m, 'login.welcome_desc')}
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="enterprise-panel py-10 px-8">
          <form className="space-y-5" onSubmit={forgotPasswordMode ? handleForgotPassword : handleLogin}>
            {error && (
              <div className="p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-400 text-sm rounded-lg">
                {error}
              </div>
            )}

            {successMessage && (
              <div className="p-3 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 text-green-700 dark:text-green-400 text-sm rounded-lg">
                {successMessage}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">
                {t(m, 'login.email')}
              </label>
              <div className="relative">
                <input
                  id="email"
                  type="email"
                  required
                  className={inputClass}
                  placeholder="name@organization.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400">
                  <span className="text-sm font-medium">@</span>
                </div>
              </div>
            </div>

            {!forgotPasswordMode && (
              <div>
                <label htmlFor="password" className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1.5">
                  {t(m, 'login.password')}
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    required={!forgotPasswordMode}
                    className={`${inputClass} pr-11`}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400">
                    <Lock size={15} strokeWidth={2} />
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>

                <div className="flex justify-end mt-2">
                  <button
                    type="button"
                    onClick={() => {
                      router.push(buildLoginPath(routing, {
                        forgot: true,
                        redirect: searchParams.get('redirect'),
                      }));
                      setError(null);
                      setSuccessMessage(null);
                    }}
                    className="text-xs font-medium text-[#d97706] hover:text-[#b45309] transition-colors"
                  >
                    {isEn ? 'Forgot password?' : 'ลืมรหัสผ่าน?'}
                  </button>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || (forgotPasswordMode && countdown > 0)}
              className="w-full py-3 btn-primary text-sm flex justify-center items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <Loader2 className="animate-spin h-4 w-4" />
              ) : forgotPasswordMode ? (
                countdown > 0
                  ? `${t(m, 'login.resend_in')} ${countdown}${isEn ? 's' : ' วินาที'}`
                  : t(m, 'login.send_reset')
              ) : (
                t(m, 'login.sign_in')
              )}
            </button>
          </form>

          {!forgotPasswordMode && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200 dark:border-slate-700" />
                </div>
                <div className="relative flex justify-center text-[10px] font-medium uppercase">
                  <span className="bg-white dark:bg-slate-900 px-3 text-slate-500 dark:text-slate-400 tracking-wide">
                    {isEn ? 'Or' : 'หรือ'}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={async () => {
                  try {
                    const { error } = await supabase.auth.signInWithOAuth({
                      provider: 'google',
                      options: {
                        redirectTo: absoluteLocaleUrl(window.location.origin, '/dashboard', routing),
                      },
                    });
                    if (error) throw error;
                  } catch (err: any) {
                    setError(err.message || 'Google login failed');
                  }
                }}
                className="w-full py-3 btn-secondary text-sm flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="#EA4335"
                    d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.41 0-6.19-2.78-6.19-6.19s2.78-6.19 6.19-6.19c1.554 0 2.969.577 4.062 1.524l3.11-3.11C19.167 1.83 15.938 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c5.897 0 10.867-4.246 10.867-11.24 0-.648-.057-1.285-.171-1.954H12.24z"
                  />
                </svg>
                {isEn ? 'Continue with Google' : 'เข้าสู่ระบบด้วย Google'}
              </button>
            </>
          )}

          <div className="mt-8 pt-5 border-t border-slate-200 dark:border-slate-700 flex flex-col items-center gap-3">
            <p className="text-xs text-slate-600 dark:text-slate-400">
              {t(m, 'login.no_account')}{' '}
              <Link href={buildRegisterPath(routing, { step: '1' })} className="font-medium text-[#d97706] hover:text-[#b45309]">
                {isEn ? 'Register' : 'สมัครสมาชิก'}
              </Link>
            </p>
            {forgotPasswordMode && (
              <button
                type="button"
                onClick={() => {
                  router.push(buildLoginPath(routing, { redirect: searchParams.get('redirect') }));
                  setError(null);
                  setSuccessMessage(null);
                }}
                className="text-xs font-medium text-slate-500 hover:text-[#d97706] transition-colors"
              >
                {t(m, 'login.back_login')}
              </button>
            )}
          </div>
        </div>

        <p className="mt-6 text-center text-[11px] text-slate-500 dark:text-slate-400">
          {isEn ? 'Encrypted connection · Your data stays isolated per account' : 'การเชื่อมต่อเข้ารหัส · ข้อมูลแยกตามบัญชีผู้ใช้'}
        </p>
      </div>

    </div>
  );
};

export default Login;
