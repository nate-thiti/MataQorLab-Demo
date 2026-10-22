// @ts-nocheck
'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter, useParams } from 'next/navigation';
import { Mail, Lock, User, Calendar, Loader2, ArrowRight, CheckCircle2, ShieldCheck, Eye, EyeOff, Phone, Globe, Cloud, Cpu, FileText, ArrowLeft, Check, Building2, Gauge, Layers3 } from '@/components/icons';
import { supabase } from '../utils/supabaseClient.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { absoluteLocaleUrl, localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import { getBrowserTimezone } from '../utils/timezone.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { calculateEnterpriseMonthlyPrice } from '../utils/enterprisePricing.js';
import PlanAudienceSwitch from '../components/PlanAudienceSwitch';
import {
  buildLegalPath,
  buildLoginPath,
  buildRegisterPath,
  isUuid,
  REGISTER_STEPS,
} from '../utils/dashboardRoutes.js';
import MQLogo from '../assets/MQ.svg';

const inputClass =
  'app-input block w-full pl-11 pr-4 py-3 text-sm';

const labelClass = 'app-field-label';

const Register = () => {
  const { step: stepParam, planId: planIdParam } = useParams();
  const step = REGISTER_STEPS.has(stepParam) ? parseInt(stepParam, 10) : 1;
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    phone: '',
    countryCode: '+66',
    birthday: '', // YYYY-MM-DD format
    planId: null,
    seats: 2,
    audience: 'individual',
    organizationName: '',
  });
  const [showPass, setShowPass] = useState(false);
  const [showConfirmPass, setShowConfirmPass] = useState(false);
  
  const [plans, setPlans] = useState<any[]>([]);
  const [countdown, setCountdown] = useState(() => {
    if (typeof window === 'undefined') return 0;
    const lastSent = localStorage.getItem('last_magic_link_sent');
    if (lastSent) {
      const diff = Math.floor((Date.now() - parseInt(lastSent, 10)) / 1000);
      if (diff < 60) return 60 - diff;
    }
    return 0;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<any>(null);
  const [success, setSuccess] = useState(false);
  const router = useRouter();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);

  const setRegistrationAudience = (audience) => {
    const normalized = audience === 'business' ? 'business' : 'individual';
    localStorage.setItem('matqor_registration_audience', normalized);
    setFormData((prev) => {
      const selectedPlan = plans.find((plan) => plan.id === prev.planId);
      const enterprisePlan = plans.find((plan) => plan.name === 'Enterprise');
      return {
        ...prev,
        audience: normalized,
        planId: normalized === 'business'
          ? (enterprisePlan?.id || prev.planId)
          : (selectedPlan?.name === 'Enterprise' ? null : prev.planId),
        seats: normalized === 'business' ? Math.max(2, prev.seats || 2) : 1,
      };
    });
  };

  const persistRegistrationIntent = () => {
    localStorage.setItem('matqor_registration_audience', formData.audience);
    if (formData.audience === 'business') {
      localStorage.setItem(
        'matqor_pending_organization_name',
        formData.organizationName.trim(),
      );
    } else {
      localStorage.removeItem('matqor_pending_organization_name');
    }
  };

  const validateBusinessIntent = () => {
    if (formData.audience !== 'business') return true;
    const length = formData.organizationName.trim().length;
    if (length >= 2 && length <= 160) return true;
    setError(isEn
      ? 'Enter an organization name between 2 and 160 characters.'
      : 'กรอกชื่อองค์กรระหว่าง 2–160 ตัวอักษร');
    return false;
  };

  // Define fetchPlans using useCallback to prevent unnecessary re-renders
  const fetchPlans = useCallback(async () => {
    try {
      const { data, error: fetchError } = await supabase.from('plans').select('*').order('price_monthly', { ascending: true });
      if (fetchError) throw fetchError;
      
      if (data && data.length > 0) {
        setPlans(data);
      } else {
        console.warn("No plans found in database.");
      }
    } catch (err: any) {
      console.error("Error fetching plans:", err);
      setError(t(m, 'register.plan_load_error'));
    }
  }, [m]);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      if (getE2eMockUser()) {
        window.location.replace(localePath('/dashboard', routing));
        return;
      }

      const { data: { user } } = await supabase.auth.getUser();
      if (cancelled) return;

      const stepNum = REGISTER_STEPS.has(stepParam) ? parseInt(stepParam, 10) : 1;

      if (!REGISTER_STEPS.has(stepParam)) {
        router.replace(buildRegisterPath(routing, { step: '1' }));
        return;
      }

      if ((stepNum === 2 || stepNum === 3) && !user) {
        router.replace(buildRegisterPath(routing, { step: '1' }));
        return;
      }

      if (user) {
        const { data: profile } = await supabase
          .from('profiles')
          .select('plan_id')
          .eq('id', user.id)
          .maybeSingle();

        if (cancelled) return;

        if (profile?.plan_id) {
          window.location.replace(localePath('/dashboard', routing));
          return;
        }

        if (user.email) {
          setFormData((prev) => ({ ...prev, email: user.email }));
        }

        if (stepNum === 1) {
          router.replace(buildRegisterPath(routing, { step: '2' }));
        }
      }
    })();

    void (async () => {
      await fetchPlans();
    })();

    return () => {
      cancelled = true;
    };
  }, [stepParam, fetchPlans, router, routing]);

  useEffect(() => {
    const audience = localStorage.getItem('matqor_registration_audience');
    const organizationName = localStorage.getItem(
      'matqor_pending_organization_name'
    ) || '';
    if (audience === 'business' || organizationName) {
      setFormData((prev) => ({
        ...prev,
        audience: 'business',
        organizationName,
        seats: Math.max(2, prev.seats || 2),
      }));
    }
  }, []);

  useEffect(() => {
    if (formData.audience !== 'business' || plans.length === 0) return;
    const enterprisePlan = plans.find((plan) => plan.name === 'Enterprise');
    if (!enterprisePlan) return;
    setFormData((prev) => (
      prev.planId === enterprisePlan.id
        ? prev
        : { ...prev, planId: enterprisePlan.id, seats: Math.max(2, prev.seats || 2) }
    ));
  }, [formData.audience, plans]);

  useEffect(() => {
    if (stepParam !== '3' || !planIdParam) return;
    if (!isUuid(planIdParam)) {
      router.replace(buildRegisterPath(routing, { step: '3' }));
      return;
    }
    if (plans.length > 0 && !plans.some((p) => p.id === planIdParam)) {
      router.replace(buildRegisterPath(routing, { step: '3' }));
      return;
    }
    if (plans.some((p) => p.id === planIdParam)) {
      setFormData((prev) => (prev.planId === planIdParam ? prev : { ...prev, planId: planIdParam }));
    }
  }, [stepParam, planIdParam, plans, router, routing]);

  useEffect(() => {
    if (stepParam !== '3' || planIdParam || plans.length === 0) return;
    const pendingPlanId = sessionStorage.getItem('matqor_pending_plan_id')
      || localStorage.getItem('matqor_pending_plan_id');
    const pendingPlan = plans.find((plan) => plan.id === pendingPlanId);
    if (!pendingPlan) return;
    const pendingSeats = Number(
      sessionStorage.getItem('matqor_pending_plan_seats')
      || localStorage.getItem('matqor_pending_plan_seats')
      || 2
    );
    setFormData((prev) => ({
      ...prev,
      planId: pendingPlan.id,
      audience: pendingPlan.name === 'Enterprise' ? 'business' : 'individual',
      organizationName: pendingPlan.name === 'Enterprise'
        ? (localStorage.getItem('matqor_pending_organization_name') || prev.organizationName)
        : '',
      seats: pendingPlan.name === 'Enterprise'
        ? Math.min(500, Math.max(2, pendingSeats || 2))
        : 1,
    }));
    router.replace(buildRegisterPath(routing, {
      step: '3',
      planId: pendingPlan.id,
    }));
  }, [stepParam, planIdParam, plans, router, routing]);

  // จัดการการนับถอยหลังทุกๆ 1 วินาที
  useEffect(() => {
    let timer;
    if (countdown > 0) {
      timer = setInterval(() => {
        setCountdown(prev => prev - 1);
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [countdown]);

  const handleChange = (e) => {
    const { id, value } = e.target;
    setFormData(prev => ({ ...prev, [id]: value }));
  };

  // ฟังก์ชันคำนวณความแข็งแรงของรหัสผ่าน (0-4)
  const getPasswordStrength = (password) => {
    let strength = 0;
    if (password.length >= 8) strength++;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) strength++;
    if (/[0-9]/.test(password)) strength++;
    if (/[^A-Za-z0-9]/.test(password)) strength++;
    return strength;
  };

  const strengthLabels = [
    t(m, 'register.strength_0', 'Too weak'),
    t(m, 'register.strength_1', 'Fair'),
    t(m, 'register.strength_2', 'Medium'),
    t(m, 'register.strength_3', 'Strong'),
    t(m, 'register.strength_4', 'Very strong')
  ];
  const strengthColors = ['bg-gray-200', 'bg-red-400', 'bg-orange-400', 'bg-yellow-400', 'bg-green-500'];
  const currentStrength = getPasswordStrength(formData.password);
  const visiblePlans = plans.filter((plan) => (
    formData.audience === 'business'
      ? plan.name === 'Enterprise'
      : plan.name !== 'Enterprise'
  ));

  const getStrengthText = () => {
    if (!formData.password) return '';
    return strengthLabels[currentStrength];
  };

  const getStrengthColor = () => {
    if (!formData.password) return 'bg-gray-200';
    return strengthColors[currentStrength];
  };

  // Step 1: ส่ง Magic Link
  const handleSendMagicLink = async (e) => {
    e.preventDefault();
    if (countdown > 0) return; // ป้องกันการกดหากยังอยู่ในช่วงนับถอยหลัง
    if (!validateBusinessIntent()) return;
    persistRegistrationIntent();

    setLoading(true);
    setError(null);

    try {
      const { error: otpError } = await supabase.auth.signInWithOtp({
        email: formData.email.trim().toLowerCase(),
        options: { emailRedirectTo: absoluteLocaleUrl(window.location.origin, '/register/step/2', routing) }
      });
      
      if (otpError) throw otpError;
      setSuccess(true);
      localStorage.setItem('last_magic_link_sent', Date.now().toString()); // บันทึกเวลาที่ส่ง
      setCountdown(60); // เริ่มนับถอยหลัง 60 วินาทีหลังจากส่งสำเร็จ
    } catch (err: any) {
      // ปรับปรุงการแจ้งเตือน Error ให้ชัดเจนและเป็นมิตรกับผู้ใช้มากขึ้น
      if (err.status === 429 || err.message?.includes('rate limit')) {
        setError(t(m, 'register.rate_limit', 'Too many requests. Please wait 1-2 minutes and try again.'));
      } else if (err.message?.includes('network') || err.message?.includes('fetch')) {
        setError(t(m, 'register.network_error', 'Cannot connect to server. Please check your internet.'));
      } else {
        setError(`${t(m, 'register.send_email_error_prefix', 'Failed to send email:')} ${err.message || ''}`.trim());
      }
    } finally {
      setLoading(false);
    }
  };

  // Step 2: บันทึกข้อมูลโปรไฟล์และตั้งรหัสผ่าน
  const handleSaveDetails = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // ตรวจสอบเบอร์โทรศัพท์ (Regex พื้นฐาน)
    const phoneRegex = /^[0-9]{9,10}$/; // Basic validation for 9-10 digits
    if (!phoneRegex.test(formData.phone)) {
      setError(t(m, 'register.invalid_phone'));
      setLoading(false);
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setError(t(m, 'register.pass_mismatch'));
      setLoading(false);
      return;
    }

    try {
      // เนื่องจากเรา Login ผ่าน Magic Link มาแล้ว (Step 1) User จึงมีตัวตนในระบบแล้ว
      // เราต้องใช้ updateUser เพื่อตั้งรหัสผ่านและเก็บ Metadata แทนการใช้ signUp
      const { data: { user: updatedUser }, error: authError } = await supabase.auth.updateUser({
        password: formData.password,
        data: {
          full_name: formData.fullName,
          phone: `${formData.countryCode}${formData.phone}`,
          birthday: formData.birthday
        }
      });

      if (authError) throw authError;

      // อัปเดตตาราง profiles (ที่ถูกสร้างอัตโนมัติโดย SQL Trigger ตั้งแต่เรายืนยันอีเมล)
      const { error: profileError } = await supabase
        .from('profiles')
        .update({
          full_name: formData.fullName,
          timezone: getBrowserTimezone(),
        })
        .eq('id', updatedUser.id);
      
      if (profileError) throw profileError;

      router.push(buildRegisterPath(routing, { step: '3' }));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: เลือกแผนและเสร็จสิ้น
  const handleFinish = async () => {
    if (loading || !formData.planId) return;
    if (!validateBusinessIntent()) return;
    persistRegistrationIntent();

    setLoading(true);
    setError(null);

    try {
      const { data: { user } } = await supabase.auth.getUser();
      const selectedPlan = plans.find(p => p.id === formData.planId);

      if (selectedPlan && selectedPlan.price_monthly > 0) {
        // แผนที่มีค่าบริการ ให้เรียกชำระเงินผ่าน Stripe Sandbox
        const { handleStripeCheckout } = await import('../utils/stripe.js');
        await handleStripeCheckout({
          user_id: user.id,
          plan_id: selectedPlan.id,
          seats: selectedPlan.name === 'Enterprise'
            ? Math.min(500, Math.max(2, Number(formData.seats) || 2))
            : 1,
          organization_name: selectedPlan.name === 'Enterprise'
            ? formData.organizationName.trim()
            : null,
        });
        sessionStorage.removeItem('matqor_pending_plan_id');
        sessionStorage.removeItem('matqor_pending_plan_seats');
        localStorage.removeItem('matqor_pending_plan_id');
        localStorage.removeItem('matqor_pending_plan_seats');
        localStorage.removeItem('matqor_pending_organization_name');
        localStorage.removeItem('matqor_registration_audience');
      } else {
        // โปรไฟล์ถูกสร้างเป็น Free โดย auth trigger อยู่แล้ว
        localStorage.removeItem('matqor_pending_plan_id');
        localStorage.removeItem('matqor_pending_plan_seats');
        localStorage.removeItem('matqor_pending_organization_name');
        localStorage.removeItem('matqor_registration_audience');
        window.location.replace(localePath('/dashboard', routing));
      }
    } catch (err: any) {
      setError(err.message);
      setLoading(false);
    }
  };

  if (success && step === 1) {
    return (
      <div className="auth-shell flex items-center justify-center p-6">
        <div className="enterprise-panel p-10 text-center max-w-md w-full">
          <div className="w-14 h-14 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900/40 rounded-lg flex items-center justify-center text-green-600 dark:text-green-400 mx-auto mb-6">
            <CheckCircle2 size={28} strokeWidth={2} />
          </div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-3">{t(m, 'register.success_title')}</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-8">
            {t(m, 'register.success_prefix')} <br />
            <span className="text-slate-900 dark:text-white font-medium">{formData.email}</span> <br />
            {t(m, 'register.success_suffix')}
          </p>
          <button onClick={() => setSuccess(false)} className="w-full py-3 btn-primary text-sm flex items-center justify-center gap-2">
            {t(m, 'register.back_register')} <ArrowRight size={16} strokeWidth={2} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell auth-shell-register flex flex-col justify-center py-12 px-6 lg:px-8 font-sans text-slate-900 dark:text-slate-100">
      
      {/* Step Indicator Header (Only shown for Step 1 and 2 to keep layout clean and matching screenshots) */}
      {(step === 1 || step === 2) && (
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          {step === 2 && (
            <div className="flex justify-center mb-4">
              <div className="w-12 h-12 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg flex items-center justify-center">
                <img src={MQLogo?.src || MQLogo} alt="MataQorLab Logo" className="w-8 h-8 object-contain" />
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="text-center mb-4">
              <span className="inline-block text-[10px] font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-600 px-3 py-1 rounded uppercase tracking-wide">
                {isEn ? 'Registration' : 'การสมัครสมาชิก'}
              </span>
            </div>
          )}
          <h2 className="text-center text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
            {step === 1 ? (isEn ? 'Create your account' : 'สร้างบัญชี') : (isEn ? 'Personal details' : 'ข้อมูลส่วนตัว')}
          </h2>
          <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-400">
            {step === 1
              ? (isEn ? 'Enter your email to get started.' : 'กรอกอีเมลเพื่อเริ่มต้นใช้งาน')
              : (isEn ? 'Step 2 of 3' : 'ขั้นตอนที่ 2 จาก 3')}
          </p>
        </div>
      )}

      {step === 3 && (
        <div className="text-center mb-8">
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-600 px-3 py-1 rounded uppercase tracking-wide mb-3">
            <Check size={10} strokeWidth={3} />
            {isEn ? 'Step 3 of 3' : 'ขั้นตอนที่ 3 จาก 3'}
          </span>
          <h2 className="text-center text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
            {isEn ? 'Choose your plan' : 'เลือกแผนที่เหมาะกับคุณ'}
          </h2>
          <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-400 max-w-xl mx-auto">
            {isEn ? 'Scale your data analysis with the right workspace limits.' : 'เลือกแผนที่ตรงกับปริมาณการใช้งานของคุณ'}
          </p>
          <div className="mx-auto mt-6 max-w-xl">
            <PlanAudienceSwitch
              value={formData.audience}
              onChange={setRegistrationAudience}
              isEn={isEn}
            />
          </div>
        </div>
      )}

      <div className={`mt-8 sm:mx-auto sm:w-full ${step === 3 ? 'sm:max-w-7xl' : 'sm:max-w-md'}`}>
        {step !== 3 ? (
          <div className="enterprise-panel py-10 px-8">
            {error && <div className="p-3 mb-4 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-400 text-sm rounded-lg">{error}</div>}

            {step === 1 && (
              <>
                <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-700 pb-3 mb-5">
                  <span className="text-[10px] font-medium tracking-wide text-slate-500 uppercase">
                    {isEn ? 'Setup' : 'ตั้งค่า'}
                  </span>
                  <span className="text-[10px] font-medium text-[#d97706] uppercase">
                    {isEn ? 'Step 1 of 3' : 'ขั้นตอน 1/3'}
                  </span>
                </div>
                <div className="progress-track h-1.5 mb-6">
                  <div className="progress-fill" style={{ width: '33.33%' }} />
                </div>

                <form onSubmit={handleSendMagicLink} className="space-y-5">
                  <PlanAudienceSwitch
                    value={formData.audience}
                    onChange={setRegistrationAudience}
                    isEn={isEn}
                    compact
                  />
                  {formData.audience === 'business' && (
                    <div>
                      <label htmlFor="organizationName" className={labelClass}>
                        {isEn ? 'Organization name' : 'ชื่อองค์กร'}
                      </label>
                      <div className="relative">
                        <input
                          id="organizationName"
                          type="text"
                          required
                          minLength={2}
                          maxLength={160}
                          value={formData.organizationName}
                          onChange={handleChange}
                          className={inputClass}
                          placeholder={isEn ? 'Acme Analytics' : 'บริษัท ตัวอย่าง จำกัด'}
                        />
                        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 dark:text-slate-500">
                          <Building2 size={15} strokeWidth={2.2} />
                        </div>
                      </div>
                    </div>
                  )}
                  <div>
                    <label className={labelClass}>{t(m, 'register.email_label', 'Registration email')}</label>
                    <div className="relative">
                      <input
                        id="email"
                        type="email"
                        required
                        value={formData.email}
                        onChange={handleChange}
                        className={inputClass}
                        placeholder="name@company.com"
                      />
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 dark:text-slate-500">
                        <Mail size={15} strokeWidth={2.5} />
                      </div>
                    </div>
                  </div>
                  
                  <button
                      type="submit"
                      disabled={loading || countdown > 0}
                      className="w-full py-3 btn-primary text-sm flex justify-center items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {loading ? (
                        <Loader2 className="animate-spin h-4 w-4" strokeWidth={2} />
                      ) : (
                        <>
                          {countdown > 0
                            ? t(m, 'register.resend_countdown', 'Resend in {count}s', { count: countdown })
                            : t(m, 'register.continue', 'Continue')}
                          <ArrowRight size={14} strokeWidth={2.5} />
                        </>
                      )}
                    </button>
                </form>

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

                <div>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!validateBusinessIntent()) return;
                      persistRegistrationIntent();
                      try {
                        const { error } = await supabase.auth.signInWithOAuth({
                          provider: 'google',
                          options: {
                            redirectTo: absoluteLocaleUrl(window.location.origin, '/register/step/2', routing),
                          }
                        });
                        if (error) throw error;
                      } catch (err: any) {
                        setError(err.message || 'Google signup failed');
                      }
                    }}
                    className="w-full py-3 btn-secondary text-sm flex items-center justify-center gap-2"
                  >
                    <svg className="w-4 h-4" viewBox="0 0 24 24">
                      <path
                        fill="#EA4335"
                        d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.41 0-6.19-2.78-6.19-6.19s2.78-6.19 6.19-6.19c1.554 0 2.969.577 4.062 1.524l3.11-3.11C19.167 1.83 15.938 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c5.897 0 10.867-4.246 10.867-11.24 0-.648-.057-1.285-.171-1.954H12.24z"
                      />
                    </svg>
                    {isEn ? 'Continue with Google' : 'สมัครด้วย Google'}
                  </button>
                </div>

                <div className="mt-8 pt-5 border-t border-slate-200 dark:border-slate-700 flex flex-col items-center">
                  <p className="text-xs text-slate-600 dark:text-slate-400">
                    {isEn ? 'Already have an account?' : 'มีบัญชีอยู่แล้ว?'}{' '}
                    <Link href={buildLoginPath(routing)} className="font-medium text-[#d97706] hover:text-[#b45309]">
                      {isEn ? 'Log in' : 'เข้าสู่ระบบ'}
                    </Link>
                  </p>
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <div className="progress-track h-1.5 mb-6 max-w-[200px] mx-auto">
                  <div className="progress-fill" style={{ width: '66.66%' }} />
                </div>

                <form onSubmit={handleSaveDetails} className="space-y-4">
                  <div>
                    <label className={labelClass}>{t(m, 'register.full_name_label', 'Full name')}</label>
                    <div className="relative">
                      <input
                        id="fullName"
                        required
                        value={formData.fullName}
                        onChange={handleChange}
                        className={inputClass}
                        placeholder={isEn ? 'Enter your full name' : 'ชื่อ-นามสกุล'}
                      />
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center text-slate-400 dark:text-slate-500 pointer-events-none">
                        <User size={15} strokeWidth={2.5} />
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className={labelClass}>{t(m, 'register.birthday_label', 'Birthday')}</label>
                      <div className="relative">
                        <input
                          id="birthday"
                          type="date"
                          required
                          value={formData.birthday}
                          onChange={handleChange}
                          className={inputClass}
                        />
                        <div className="absolute inset-y-0 left-0 pl-4 flex items-center text-slate-400 dark:text-slate-500 pointer-events-none">
                          <Calendar size={15} strokeWidth={2.5} />
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className={labelClass}>{t(m, 'register.phone_label', 'Phone number')}</label>
                      <div className="relative">
                        <input
                          id="phone"
                          required
                          value={formData.phone}
                          onChange={handleChange}
                          className={inputClass}
                          placeholder="0812345678"
                        />
                        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 dark:text-slate-500">
                          <Phone size={15} strokeWidth={2.5} />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className={labelClass}>{t(m, 'register.new_password_label', 'New password')}</label>
                    <div className="relative">
                      <input
                        id="password"
                        type={showPass ? 'text' : 'password'}
                        required
                        value={formData.password}
                        onChange={handleChange}
                        className={`${inputClass} pr-11`}
                        placeholder="••••••••"
                        minLength={6}
                      />
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 dark:text-slate-500">
                        <Lock size={15} strokeWidth={2.5} />
                      </div>
                      <button type="button" onClick={() => setShowPass(!showPass)} className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-400 hover:text-slate-655 dark:hover:text-slate-200">
                        {showPass ? <EyeOff size={16} strokeWidth={2} /> : <Eye size={16} strokeWidth={2} />}
                      </button>
                    </div>
                    {/* Password Strength Meter */}
                    {formData.password && (
                      <div className="mt-2.5 px-1">
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-[9px] font-medium text-slate-500 uppercase">{t(m, 'register.password_strength', 'Strength')}: {getStrengthText()}</span>
                        </div>
                        <div className="flex gap-1 h-1">
                          {[1, 2, 3, 4].map((level) => (
                            <div
                              key={level}
                              className={`h-full flex-1 rounded-sm transition-all duration-500 ${currentStrength >= level ? getStrengthColor() : 'bg-slate-200 dark:bg-slate-700'}`}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className={labelClass}>{t(m, 'register.confirm_password_label', 'Confirm password')}</label>
                    <div className="relative">
                      <input
                        id="confirmPassword"
                        type={showConfirmPass ? 'text' : 'password'}
                        required
                        value={formData.confirmPassword}
                        onChange={handleChange}
                        className={`${inputClass} pr-11`}
                        placeholder="••••••••"
                      />
                      <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-455 dark:text-slate-500">
                        <ShieldCheck size={15} strokeWidth={2.5} />
                      </div>
                      <button type="button" onClick={() => setShowConfirmPass(!showConfirmPass)} className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-400 hover:text-slate-655 dark:hover:text-slate-200">
                        {showConfirmPass ? <EyeOff size={16} strokeWidth={2} /> : <Eye size={16} strokeWidth={2} />}
                      </button>
                    </div>
                  </div>

                  <div className="flex gap-3 pt-4">
                    <button
                      type="button"
                      onClick={() => router.push(buildRegisterPath(routing, { step: '1' }))}
                      className="flex-1 py-3 btn-secondary text-sm flex items-center justify-center gap-1.5"
                    >
                      <ArrowLeft size={14} strokeWidth={2.5} /> {isEn ? 'Back' : 'ย้อนกลับ'}
                    </button>
                    <button
                      type="submit"
                      disabled={loading}
                      className="flex-[2] py-3 btn-primary text-sm flex items-center justify-center gap-1.5"
                    >
                      {loading ? <Loader2 className="animate-spin h-4 w-4" /> : (isEn ? 'Continue' : 'ดำเนินการต่อ')}
                      <ArrowRight size={14} strokeWidth={2.5} />
                    </button>
                  </div>
                </form>

                <div className="mt-8 pt-5 border-t border-slate-200 dark:border-slate-700">
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 text-center leading-relaxed">
                    {isEn ? 'Your data is processed in accordance with our privacy policy.' : 'ข้อมูลของคุณได้รับการประมวลผลตามนโยบายความเป็นส่วนตัว'}
                  </p>
                </div>
              </>
            )}
          </div>
        ) : (
          <div>
            {error && <div className="p-3 mb-6 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-400 text-sm rounded-lg">{error}</div>}

            {plans.length === 0 && !error && (
              <div className="py-16 text-center enterprise-panel">
                <div className="flex flex-col items-center gap-2.5">
                  <Loader2 className="animate-spin text-slate-500 w-8 h-8" />
                  <p className="text-slate-600 dark:text-slate-400 text-sm">{t(m, 'register.loading_plans', 'Loading plans from server...')}</p>
                </div>
              </div>
            )}

            {formData.audience === 'business' && (
              <div className="mx-auto mb-6 max-w-2xl enterprise-panel p-5">
                <label htmlFor="organizationName" className={labelClass}>
                  {isEn ? 'Organization name' : 'ชื่อองค์กร'}
                </label>
                <div className="relative">
                  <input
                    id="organizationName"
                    type="text"
                    required
                    minLength={2}
                    maxLength={160}
                    value={formData.organizationName}
                    onChange={handleChange}
                    className={inputClass}
                    placeholder={isEn ? 'Acme Analytics' : 'บริษัท ตัวอย่าง จำกัด'}
                  />
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 dark:text-slate-500">
                    <Building2 size={15} strokeWidth={2.2} />
                  </div>
                </div>
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                  {isEn
                    ? 'Your organization and General workspace are created automatically after Stripe confirms payment.'
                    : 'ระบบจะสร้าง Organization และ General Workspace อัตโนมัติหลัง Stripe ยืนยันการชำระเงิน'}
                </p>
              </div>
            )}

            <div className={`grid grid-cols-1 gap-6 items-stretch ${
              formData.audience === 'business'
                ? 'mx-auto max-w-2xl'
                : 'md:grid-cols-2 xl:grid-cols-3'
            }`}>
              {visiblePlans.map((p) => {
                const isRecommended = p.name === 'Plus';
                const isEnterprise = p.name === 'Enterprise';
                const enterprisePricing = isEnterprise
                  ? calculateEnterpriseMonthlyPrice(p, formData.seats)
                  : null;
                const subtitle = p.name === 'Free'
                  ? 'ESSENTIAL'
                  : p.name === 'Plus'
                    ? 'ADVANCED INTELLIGENCE'
                    : p.name === 'Pro'
                      ? 'PROFESSIONAL POWER'
                      : 'ENTERPRISE TEAM';
                
                const features = p.name === 'Free' ? [
                  { text: '200,005 tokens (Refresh ทุกวัน)', icon: CheckCircle2 },
                  { text: 'Basic reasoning capabilities', icon: CheckCircle2 },
                  { text: '1MB upload space', icon: FileText },
                  { text: 'Excel, CSV, JSON analysis', icon: CheckCircle2 },
                ] : p.name === 'Plus' ? [
                  { text: '400,005 tokens (Refresh ทุกวัน)', icon: CheckCircle2 },
                  { text: 'Auto Web Search', icon: Globe },
                  { text: 'Complex reasoning model', icon: Gauge },
                  { text: '200MB upload space', icon: Cloud },
                  { text: 'Excel, CSV, JSON, PARQUET', icon: CheckCircle2 },
                  { text: 'External API Connection', icon: Cpu },
                ] : p.name === 'Pro' ? [
                  { text: '1,000,000 tokens (Refresh ทุกวัน)', icon: CheckCircle2 },
                  { text: 'Auto Web Search', icon: Globe },
                  { text: 'Maximum complex reasoning', icon: Gauge },
                  { text: '500MB upload space', icon: Cloud },
                  { text: 'PARQUET & Advanced formats', icon: CheckCircle2 },
                  { text: 'External SQL Server Connection', icon: Cpu },
                ] : [
                  { text: '2,000,000 tokens (Refresh ทุกวัน)', icon: CheckCircle2 },
                  { text: 'Organization workspace', icon: Globe },
                  { text: 'Governed company memory', icon: Layers3 },
                  { text: '2GB upload space', icon: Cloud },
                  { text: 'API & SQL connectors', icon: Cpu },
                  { text: 'Priority support', icon: ShieldCheck },
                ];

                return (
                  <div
                    key={p.id}
                    onClick={() => {
                      setFormData((prev) => ({
                        ...prev,
                        planId: p.id,
                        seats: isEnterprise ? Math.max(2, prev.seats || 2) : 1,
                      }));
                      router.replace(buildRegisterPath(routing, { step: '3', planId: p.id }));
                    }}
                    className={`p-6 rounded-xl border transition-colors cursor-pointer relative flex flex-col justify-between ${
                      formData.planId === p.id
                        ? 'border-[#d97706] bg-amber-50/30 dark:bg-amber-950/10'
                        : isRecommended
                          ? 'border-slate-300 dark:border-slate-600 enterprise-panel'
                          : 'enterprise-panel hover:border-slate-300 dark:hover:border-slate-500'
                    }`}
                  >
                    {isRecommended && (
                      <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[#d97706] text-white text-[9px] font-medium px-3 py-1 rounded uppercase tracking-wide">
                        {isEn ? 'Recommended' : 'แนะนำ'}
                      </div>
                    )}

                    <div>
                      <span className="text-[10px] font-medium text-slate-500 tracking-wide block mb-1">
                        {subtitle}
                      </span>
                      <h4 className="text-xl font-semibold mb-1 text-slate-900 dark:text-slate-100">{p.name}</h4>
                      <p className="text-xl font-semibold mb-5 text-slate-900 dark:text-white flex items-baseline gap-1">
                        {p.price_monthly} USD
                        <span className="text-xs font-medium text-slate-500">
                          {isEnterprise
                            ? (isEn ? '/organization/mo' : '/องค์กร/เดือน')
                            : `/${routing.locale === 'th' ? 'เดือน' : 'mo'}`}
                        </span>
                      </p>

                      {isEnterprise && formData.planId === p.id && (
                        <div
                          className="mb-5 rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <p className="text-xs text-slate-500">
                            {isEn
                              ? `${enterprisePricing.includedSeats} seats included; ${enterprisePricing.additionalSeatPrice} USD/month per additional seat`
                              : `รวม ${enterprisePricing.includedSeats} Seats; Seat เพิ่ม ${enterprisePricing.additionalSeatPrice} USD/เดือน`}
                          </p>
                          <label htmlFor="enterprise-register-seats" className="block text-xs font-medium text-slate-600 dark:text-slate-300">
                            {isEn ? 'Users (minimum 2)' : 'จำนวนผู้ใช้ (ขั้นต่ำ 2)'}
                          </label>
                          <input
                            id="enterprise-register-seats"
                            type="number"
                            min={2}
                            max={500}
                            value={formData.seats}
                            onChange={(event) => setFormData((prev) => ({
                              ...prev,
                              seats: Math.min(500, Math.max(2, Number(event.target.value) || 2)),
                            }))}
                            className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                          />
                          <p className="text-xs text-slate-500">
                            {isEn ? 'Total' : 'รวม'}:{' '}
                            <strong>{enterprisePricing.monthlyTotal} USD/{isEn ? 'month' : 'เดือน'}</strong>
                          </p>
                        </div>
                      )}

                      <ul className="space-y-3 text-xs text-slate-600 dark:text-slate-400 mb-6">
                        {features.map((f, i) => {
                          const Icon = f.icon;
                          return (
                            <li key={i} className="flex items-start gap-2.5">
                              <Icon size={14} className="text-slate-500 dark:text-slate-400 mt-0.5 shrink-0" strokeWidth={2} />
                              <span>{f.text}</span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>

                    <div className={`w-full py-2.5 rounded-lg text-xs font-medium text-center border transition-colors ${
                      formData.planId === p.id
                        ? 'bg-[#d97706] border-[#d97706] text-white'
                        : 'border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/60'
                    }`}>
                      {formData.planId === p.id
                        ? t(m, 'register.selected', 'Selected')
                        : t(m, 'register.select_plan', 'Select plan')}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="enterprise-panel p-5 mt-8">
              <p className="text-xs text-slate-600 dark:text-slate-400 text-center md:text-left">
                {isEn ? 'Enterprise is now self-service from 2 users.' : 'Enterprise สมัครเองได้แล้ว เริ่มต้นขั้นต่ำ 2 ผู้ใช้'}{' '}
                <span className="text-slate-500 dark:text-slate-500 block md:inline">
                  {isEn ? 'Contact support after signup for dedicated, white-label, or on-premise deployments.' : 'หากต้องการ Dedicated, White-label หรือ On-premise สามารถติดต่อ Support หลังสมัครได้'}
                </span>
              </p>
            </div>

            <div className="mt-8">
              <button
                onClick={handleFinish}
                disabled={!formData.planId || loading}
                className="w-full py-3.5 btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-1.5"
              >
                {loading ? (
                  <Loader2 className="animate-spin h-5 w-5 mx-auto" strokeWidth={2} />
                ) : plans.find(p => p.id === formData.planId)?.price_monthly > 0 ? (
                  isEn ? 'Proceed to Payment' : 'ไปหน้าชำระเงิน'
                ) : (
                  t(m, 'register.finish_dashboard', 'Finish & Go to Dashboard')
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {(step === 1 || step === 2) && (
        <div className="mt-8 text-center text-[11px] text-slate-500 dark:text-slate-400">
          <p>
            {isEn ? 'By continuing, you agree to our' : 'การดำเนินการต่อถือว่ายอมรับ'}{' '}
            <Link href={buildLegalPath(routing, 'terms')} className="text-[#d97706] hover:underline">
              {isEn ? 'Terms of Service' : 'ข้อกำหนดการใช้งาน'}
            </Link>
            {isEn ? ' and ' : ' และ '}
            <Link href={buildLegalPath(routing, 'privacy')} className="text-[#d97706] hover:underline">
              {isEn ? 'Privacy Policy' : 'นโยบายความเป็นส่วนตัว'}
            </Link>
          </p>
        </div>
      )}
    </div>
  );
};

export default Register;
