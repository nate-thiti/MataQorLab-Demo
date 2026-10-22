// @ts-nocheck
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { supabase } from '../utils/supabaseClient.js';
import { useTheme } from '../context/ThemeContext';
import { Camera, CreditCard, SunMoon, Shield, User as UserIcon, Copy, Check, X, Layers3, Gauge, Building2 } from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { absoluteLocaleUrl, localePath } from '../utils/locale.js';
import { buildSettingsPath, buildPaymentHistoryPath, SETTINGS_SECTIONS } from '../utils/dashboardRoutes.js';
import { getMessages, t } from '../utils/i18n.js';
import DashboardSidebar from '../components/DashboardSidebar';
import LocaleSwitcher from '../components/LocaleSwitcher';
import { DeleteConfirmationModal } from '../components/ChatModals';
import ChatMemoryPanel from '../features/chat/ChatMemoryPanel';
import AnalysisPreferencesSettings from '../components/settings/AnalysisPreferencesSettings';
import OrganizationWorkspaceSettings from '../components/settings/OrganizationWorkspaceSettings';
import { useAppSidebar } from '../context/AppSidebarContext';
import { useFileManagerCache } from '../context/FileManagerCacheContext';
import { randomUploadFilename } from '../utils/randomId.js';
import { getE2eMockUser } from '../utils/e2eAuth.js';
import { getAuthHeaders } from '../utils/authFetch.js';
import { getPublicApiUrl } from '../utils/env.js';

// Helper function สำหรับประมวลผลการ Crop เป็น Blob
const getCroppedImg = async (imageSrc, pixelCrop) => {
  const image = await new Promise((resolve, reject) => {
    const img = new Image();
    img.addEventListener('load', () => resolve(img));
    img.addEventListener('error', (error) => reject(error));
    img.src = imageSrc;
  });

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  if (!ctx) return null;

  canvas.width = pixelCrop.width;
  canvas.height = pixelCrop.height;

  ctx.drawImage(
    image,
    pixelCrop.x,
    pixelCrop.y,
    pixelCrop.width,
    pixelCrop.height,
    0,
    0,
    pixelCrop.width,
    pixelCrop.height
  );

  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      resolve(blob);
    }, 'image/jpeg', 0.9);
  });
};

const SettingsPage = () => {
  const router = useRouter();
  const { section } = useParams();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);
  const { theme, toggleTheme } = useTheme();
  
  const [user, setUser] = useState<any>(null);
  const { isOpen: isSidebarOpen, setIsOpen: setIsSidebarOpen } = useAppSidebar();
  const fileManagerCache = useFileManagerCache();
  const [plan, setPlan] = useState({ name: 'Free', storage_limit_mb: 1, message_limit: 200000 });
  const [loading, setLoading] = useState(false);
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [birthday, setBirthday] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [isCurrentPasswordVerified, setIsCurrentPasswordVerified] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [forgotPasswordMode, setForgotPasswordMode] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [showSuccess, setShowSuccess] = useState(false);
  const [successText, setSuccessText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [isCancelConfirmOpen, setIsCancelConfirmOpen] = useState(false);
  const [accountIdCopied, setAccountIdCopied] = useState(false);
  const [showMemoryPanel, setShowMemoryPanel] = useState(false);
  const [hasOrganizationAccess, setHasOrganizationAccess] = useState(false);
  const [organizationAccessChecked, setOrganizationAccessChecked] = useState(false);

  // Business/company product surface: Enterprise plan, or already invited into an org.
  const isCompanyPlan = String(plan?.name || '').toLowerCase().includes('enterprise');
  const showOrganizationSection = isCompanyPlan || hasOrganizationAccess;

  const settingsNav = [
    { id: 'profile', label: isEn ? 'Profile' : 'โปรไฟล์', Icon: UserIcon },
    { id: 'analysis', label: isEn ? 'Analysis' : 'วิเคราะห์', Icon: Gauge },
    { id: 'memory', label: isEn ? 'Memory' : 'ความจำ', Icon: Layers3 },
    ...(showOrganizationSection
      ? [{ id: 'organization', label: isEn ? 'Organization' : 'องค์กร', Icon: Building2 }]
      : []),
    { id: 'security', label: isEn ? 'Security' : 'ความปลอดภัย', Icon: Shield },
    { id: 'plan', label: isEn ? 'Plan' : 'แผน', Icon: CreditCard },
    { id: 'appearance', label: isEn ? 'Appearance' : 'ธีม', Icon: SunMoon },
  ];

  const jumpToSection = (sectionId) => {
    router.replace(buildSettingsPath(routing, sectionId === 'profile' ? null : sectionId));
  };

  const fieldClass =
    'app-input w-full px-3 py-3 text-sm font-sans';

  const activeSection = (() => {
    if (!section || !SETTINGS_SECTIONS.has(section)) return 'profile';
    if (section === 'organization' && !showOrganizationSection) {
      return organizationAccessChecked ? 'profile' : null;
    }
    return section;
  })();

  // States สำหรับระบบ Crop
  const [imageToCrop, setImageToCrop] = useState<any>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<any>(null);
  const [CropperComponent, setCropperComponent] = useState<any>(null);

  useEffect(() => {
    if (section && !SETTINGS_SECTIONS.has(section)) {
      router.replace(buildSettingsPath(routing));
    }
  }, [section, router, routing]);

  useEffect(() => {
    if (section === 'organization' && organizationAccessChecked && !showOrganizationSection) {
      router.replace(buildSettingsPath(routing));
    }
  }, [section, organizationAccessChecked, showOrganizationSection, router, routing]);

  useEffect(() => {
    let cancelled = false;
    const loadOrganizationAccess = async () => {
      if (!user?.id) {
        setHasOrganizationAccess(false);
        setOrganizationAccessChecked(false);
        return;
      }
      if (isCompanyPlan) {
        setHasOrganizationAccess(true);
        setOrganizationAccessChecked(true);
        return;
      }
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${getPublicApiUrl()}/api/v1/governance/context`, {
          method: 'GET',
          headers,
        });
        if (!response.ok) {
          if (!cancelled) {
            setHasOrganizationAccess(false);
            setOrganizationAccessChecked(true);
          }
          return;
        }
        const payload = await response.json().catch(() => ({}));
        if (!cancelled) {
          setHasOrganizationAccess(Boolean(payload.organizations?.length));
          setOrganizationAccessChecked(true);
        }
      } catch {
        if (!cancelled) {
          setHasOrganizationAccess(false);
          setOrganizationAccessChecked(true);
        }
      }
    };
    loadOrganizationAccess();
    return () => {
      cancelled = true;
    };
  }, [user?.id, isCompanyPlan]);

  // ดึงข้อมูลผู้ใช้และแผนการใช้งาน
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
        const cached = fileManagerCache.getSettingsProfile(cachedAuth.user.id);
        const metadata = cached?.profile || cachedAuth.user?.user_metadata || {};
        setFullName(metadata.full_name || '');
        setPhone(metadata.phone || '');
        setBirthday(metadata.birthday || '');
        setAvatarUrl(metadata.avatar_url || '');
        if (cached?.plan) setPlan(cached.plan);
        if (cachedAuth.isFresh && cached) return;
      }
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        setUser(user);
        fileManagerCache.setAuthUser(user);
        const cached = fileManagerCache.getSettingsProfile(user.id);
        const metadata = cached?.profile || user?.user_metadata || {};
        setFullName(metadata.full_name || '');
        setPhone(metadata.phone || '');
        setBirthday(metadata.birthday || '');
        setAvatarUrl(metadata.avatar_url || '');
        if (cached?.plan) setPlan(cached.plan);
        fileManagerCache.setSettingsProfile(user.id, { profile: user?.user_metadata || {} });

        // ดึงข้อมูลแผน
        if (cached?.isFresh) return;
        try {
          const { data: profileData } = await supabase
            .from('profiles')
            .select(`
              plan_id,
              subscription_seats,
              plans (
                name,
                storage_limit_mb,
                message_limit
              )
            `)
            .eq('id', user.id)
            .maybeSingle();

          if (profileData?.plans) {
            const planData = Array.isArray(profileData.plans) ? profileData.plans[0] : profileData.plans;
            const planWithSeats = {
              ...planData,
              subscription_seats: profileData.subscription_seats || 1,
            };
            setPlan(planWithSeats);
            fileManagerCache.setSettingsProfile(user.id, {
              profile: user?.user_metadata || {},
              plan: planWithSeats,
            });
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

  useEffect(() => {
    let mounted = true;
    if (typeof window !== 'undefined') {
      import('react-easy-crop').then((mod) => {
        if (mounted) setCropperComponent(() => mod.default);
      });
    }
    return () => {
      mounted = false;
    };
  }, []);

  const handleLogout = async () => {
    if (user?.id) fileManagerCache.clearUser(user.id);
    fileManagerCache.clearAuthUser();
    await supabase.auth.signOut();
    router.replace(localePath('/login', routing));
  };

  const handleCopyAccountId = async () => {
    if (!user?.id) return;
    try {
      await navigator.clipboard.writeText(user.id);
      setAccountIdCopied(true);
      setTimeout(() => setAccountIdCopied(false), 2000);
    } catch {
      setMessage({ type: 'error', text: t(m, 'settings.account_id_copy_failed', 'Unable to copy account ID') });
    }
  };

  const triggerSuccess = (text) => {
    setSuccessText(text);
    setShowSuccess(true);
    setMessage({ type: '', text: '' });
    setTimeout(() => setShowSuccess(false), 3000);
  };

  const onFileChange = async (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = () => {
        setImageToCrop(reader.result);
        setMessage({ type: '', text: '' });
      };
      reader.readAsDataURL(file);
    }
  };

  const onCropComplete = useCallback((croppedArea, croppedAreaPixels) => {
    setCroppedAreaPixels(croppedAreaPixels);
  }, []);

  const handleConfirmCrop = async () => {
    try {
      setUploading(true);
      const oldAvatarUrl = user?.user_metadata?.avatar_url;

      if (!croppedAreaPixels) return;

      const croppedImageBlob = await getCroppedImg(imageToCrop, croppedAreaPixels);
      const fileName = randomUploadFilename('jpg');
      const form = new FormData();
      form.append('file', croppedImageBlob, fileName);
      const headers = await getAuthHeaders();
      delete headers['Content-Type'];
      const uploadResponse = await fetch(`${getPublicApiUrl()}/api/v1/files/avatar`, {
        method: 'POST',
        headers,
        body: form,
      });
      const uploadPayload = await uploadResponse.json().catch(() => ({}));
      if (!uploadResponse.ok) throw new Error(uploadPayload.detail || t(m, 'settings.avatar_upload_failed', 'Avatar upload failed'));
      const filePath = uploadPayload.path;
      const publicUrl = uploadPayload.public_url;

      setAvatarUrl(publicUrl);
      
      await supabase.auth.updateUser({
        data: { avatar_url: publicUrl }
      });
      if (user?.id) {
        fileManagerCache.setSettingsProfile(user.id, {
          profile: { ...(user.user_metadata || {}), avatar_url: publicUrl },
          plan,
        });
      }

      if (oldAvatarUrl && oldAvatarUrl.includes('/avatars/')) {
        try {
          const oldPath = oldAvatarUrl.split('/avatars/').pop();
          if (oldPath) {
            await supabase.storage.from('avatars').remove([oldPath]);
          }
        } catch (deleteError: unknown) {
          console.error('Error deleting old avatar file:', deleteError);
        }
      }

      triggerSuccess(t(m, 'settings.upload_success', 'Profile image uploaded successfully'));
      setImageToCrop(null);
    } catch (error: any) {
      setMessage({ type: 'error', text: `${t(m, 'settings.upload_failed', 'Upload failed:')} ${error.message}` });
    } finally {
      setUploading(false);
    }
  };

  const handleVerifyCurrentPassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage({ type: '', text: '' });

    const { error } = await supabase.auth.signInWithPassword({
      email: user?.email,
      password: currentPassword,
    });

    if (error) {
      setMessage({ type: 'error', text: t(m, 'settings.password_wrong', 'Current password is incorrect') });
    } else {
      setIsCurrentPasswordVerified(true);
      triggerSuccess(t(m, 'settings.verified', 'Verification successful. Please set a new password.'));
    }
    setLoading(false);
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage({ type: '', text: '' });

    const nextProfile = {
      full_name: fullName,
      phone: phone,
      birthday: birthday,
      avatar_url: avatarUrl
    };
    const { error } = await supabase.auth.updateUser({
      data: nextProfile
    });

    if (error) {
      setMessage({ type: 'error', text: error.message });
    } else {
      if (user?.id) {
        fileManagerCache.setSettingsProfile(user.id, { profile: nextProfile, plan });
      }
      triggerSuccess(t(m, 'settings.profile_saved', 'Profile updated successfully'));
    }
    setLoading(false);
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage({ type: '', text: '' });

    const { error } = await supabase.auth.resetPasswordForEmail(user?.email, {
      redirectTo: absoluteLocaleUrl(window.location.origin, '/reset-password', routing),
    });

    if (error) {
      setMessage({ type: 'error', text: error.message });
    } else {
      triggerSuccess(t(m, 'settings.reset_sent', 'Reset password link sent to your email'));
    }
    setLoading(false);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (!newPassword) return;
    setLoading(true);
    setMessage({ type: '', text: '' });

    const { error } = await supabase.auth.updateUser({
      password: newPassword
    });

    if (error) {
      setMessage({ type: 'error', text: error.message });
    } else {
      triggerSuccess(t(m, 'settings.password_changed', 'Password changed successfully'));
      setNewPassword('');
    }
    setLoading(false);
  };

  const handleCancel = async () => {
    if (!user) return;
    setIsCancelConfirmOpen(true);
  };

  const confirmCancelSubscription = async () => {
    setIsCancelConfirmOpen(false);
    setLoading(true);
    setMessage({ type: '', text: '' });
    try {
      const { handleCancelSubscription } = await import('../utils/stripe.js');
      await handleCancelSubscription({ user_id: user.id });
      triggerSuccess(t(m, 'settings.cancel_success', 'Subscription canceled successfully.'));
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (err: any) {
      console.error(err);
      setMessage({ type: 'error', text: err.message || 'Failed to cancel subscription' });
    } finally {
      setLoading(false);
    }
  };

  const handleViewBilling = () => {
    router.push(buildPaymentHistoryPath(routing));
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
        {/* Page Title */}
        <div className="mb-8 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="min-w-0">
            <div className="app-page-kicker mb-3">ACCOUNT CONTROL</div>
            <h1 className="text-xl font-semibold text-slate-900 dark:text-white tracking-tight">
              {t(m, 'settings.account_title', 'Account Settings')}
            </h1>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 max-w-2xl">
                {isEn
                ? (showOrganizationSection
                  ? 'Manage profile, analysis defaults, memory, organization access, plan, security, and appearance.'
                  : 'Manage profile, analysis defaults, memory, plan, security, and appearance.')
                : (showOrganizationSection
                  ? 'จัดการโปรไฟล์ ค่าวิเคราะห์ ความจำ สิทธิ์องค์กร แผน ความปลอดภัย และรูปลักษณ์'
                  : 'จัดการโปรไฟล์ ค่าวิเคราะห์ ความจำ แผน ความปลอดภัย และรูปลักษณ์')}
            </p>
          </div>
          <span className="inline-flex self-start items-center rounded-lg border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-zinc-900/70 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
            {plan?.name || 'Free'} {t(m, 'settings.current_plan', 'Current plan')}
          </span>
        </div>

        <nav
          aria-label={isEn ? 'Settings sections' : 'ส่วนการตั้งค่า'}
          className="mb-6 flex gap-2 overflow-x-auto pb-1"
        >
          {settingsNav.map(({ id, label, Icon }) => {
            const active = activeSection === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => jumpToSection(id)}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                  active
                    ? 'border-amber-500/50 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/35 dark:text-amber-200'
                    : 'border-slate-200 bg-white/80 text-slate-600 hover:border-amber-300 hover:text-amber-800 dark:border-white/10 dark:bg-zinc-900/70 dark:text-slate-300 dark:hover:border-amber-800 dark:hover:text-amber-200'
                }`}
              >
                <Icon size={13} strokeWidth={1.7} />
                {label}
              </button>
            );
          })}
        </nav>

        {/* Global Error Banner */}
        {message.text && message.type === 'error' && (
          <div className="p-4 mb-6 rounded-xl text-sm bg-red-50 border border-red-200 text-red-600 dark:bg-red-950/20 dark:border-red-900/30 dark:text-red-400">
            {message.text}
          </div>
        )}

        <div className="mx-auto w-full max-w-3xl space-y-6">
          {activeSection === 'profile' && (
            <>
            <div id="settings-profile" className="enterprise-panel p-6 md:p-8 space-y-6">
              <div className="flex items-center gap-3 border-b border-slate-200/80 dark:border-white/10 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <UserIcon size={18} strokeWidth={1.6} />
                </div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(m, 'settings.profile', 'Profile Information')}
                </h2>
              </div>

              <div className="flex items-center gap-5 p-4 bg-slate-50/80 dark:bg-zinc-900/50 rounded-xl border border-slate-200/70 dark:border-white/10">
                <div className="relative group flex-shrink-0">
                  <div className="w-20 h-20 rounded-full bg-amber-50 dark:bg-zinc-800 border border-slate-200 dark:border-white/10 overflow-hidden flex items-center justify-center">
                    {avatarUrl ? (
                      <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-xl font-semibold text-[#d97706] dark:text-amber-300">
                        {fullName?.charAt(0) || user?.email?.charAt(0).toUpperCase() || '?'}
                      </span>
                    )}
                  </div>
                  <label className="absolute inset-0 flex items-center justify-center bg-black/40 text-white rounded-full opacity-0 group-hover:opacity-100 cursor-pointer transition-opacity">
                    <input type="file" className="hidden" accept="image/*" onChange={onFileChange} disabled={uploading} />
                    <Camera className="w-5 h-5" strokeWidth={1.5} />
                  </label>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-white">{isEn ? 'Avatar Image' : 'รูปประจำตัว'}</h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {uploading ? t(m, 'settings.uploading', 'Uploading...') : t(m, 'settings.click_change', 'Hover image & click icon to change')}
                  </p>
                </div>
              </div>

              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div>
                  <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">{t(m, 'settings.full_name', 'Full name')}</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className={fieldClass}
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">{t(m, 'settings.phone', 'Phone')}</label>
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className={fieldClass}
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">{t(m, 'settings.birthday', 'Birthday')}</label>
                    <input
                      type="date"
                      value={birthday}
                      disabled
                      title={t(m, 'settings.birthday_lock', 'Birthday cannot be edited')}
                      className={`${fieldClass} cursor-not-allowed opacity-70`}
                    />
                  </div>
                </div>
                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 btn-primary text-sm disabled:opacity-50"
                  >
                    {t(m, 'settings.save_changes', 'Save changes')}
                  </button>
                </div>
              </form>
            </div>

            {user?.id && (
              <div className="enterprise-panel p-6 flex flex-col gap-2">
                <p className="text-[11px] text-slate-500 dark:text-slate-400 uppercase font-medium tracking-wider">
                  {t(m, 'settings.account_id', 'Account ID')}
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <code className="text-xs text-slate-600 dark:text-slate-300 font-mono bg-slate-50 dark:bg-zinc-800 px-2 py-1 rounded-lg border border-slate-200/70 dark:border-white/10">
                    {user.id}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopyAccountId}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 border border-slate-200 dark:border-white/12 rounded-lg transition-colors"
                    title={t(m, 'settings.account_id_copy', 'Copy account ID')}
                  >
                    {accountIdCopied ? (
                      <>
                        <Check size={13} className="text-green-600" />
                        {t(m, 'settings.account_id_copied', 'Copied')}
                      </>
                    ) : (
                      <>
                        <Copy size={13} />
                        {t(m, 'settings.account_id_copy', 'Copy')}
                      </>
                    )}
                  </button>
                </div>
                <p className="text-[11px] text-slate-400 dark:text-slate-400 font-sans">
                  {t(m, 'settings.account_id_support_hint', 'Use this ID when contacting support')}
                </p>
              </div>
            )}
            </>
          )}

          {activeSection === 'security' && (
            <div id="settings-security" className="enterprise-panel p-6 md:p-8 space-y-6">
              <div className="flex items-center gap-3 border-b border-slate-200/80 dark:border-white/10 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <Shield size={18} strokeWidth={1.6} />
                </div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(m, 'settings.security', 'Security & Authentication')}
                </h2>
              </div>

              {forgotPasswordMode ? (
                <div className="space-y-4">
                  <p className="text-xs text-slate-500 dark:text-slate-450 leading-relaxed">
                    {t(m, 'settings.reset_desc', 'We will send a reset password link to your registered email:')} <br/>
                    <strong className="text-slate-900 dark:text-white text-sm">{user?.email}</strong>
                  </p>
                  <button
                    onClick={handleForgotPassword}
                    disabled={loading}
                    className="w-full py-3 btn-primary text-sm"
                  >
                    {loading ? t(m, 'settings.sending', 'Sending...') : t(m, 'settings.send_reset', 'Send reset link')}
                  </button>
                  <button 
                    onClick={() => setForgotPasswordMode(false)}
                    className="w-full text-xs text-slate-400 hover:underline"
                  >
                    {t(m, 'settings.back_change_password', 'Back to password change')}
                  </button>
                </div>
              ) : !isCurrentPasswordVerified ? (
                <form onSubmit={handleVerifyCurrentPassword} className="space-y-4">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">{t(m, 'settings.current_password', 'Current password')}</label>
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder={t(m, 'settings.current_password_placeholder', 'Enter current password to continue')}
                      className={fieldClass}
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 btn-secondary text-sm"
                  >
                    {t(m, 'settings.verify_current_password', 'Verify current password')}
                  </button>
                  <button 
                    type="button"
                    onClick={() => setForgotPasswordMode(true)}
                    className="w-full text-xs font-semibold text-[#d97706] hover:underline"
                  >
                    {t(m, 'settings.forgot_password', 'Forgot password?')}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">{t(m, 'settings.new_password', 'New password')}</label>
                    <input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder={t(m, 'settings.new_password_placeholder', 'Enter your new password')}
                      className={fieldClass}
                      required
                    />
                  </div>
                  <div className="flex gap-4">
                    <button
                      type="button"
                      onClick={() => { setIsCurrentPasswordVerified(false); setCurrentPassword(''); }}
                      className="flex-1 py-3 btn-secondary text-sm"
                    >
                      {t(m, 'settings.cancel', 'Cancel')}
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !newPassword}
                      className="flex-[2] py-3 btn-primary text-sm disabled:opacity-30"
                    >
                      {t(m, 'settings.update_password', 'Update password')}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {activeSection === 'analysis' && (
            <AnalysisPreferencesSettings
              userId={user?.id}
              isEn={isEn}
              onSaved={(text) => triggerSuccess(text)}
            />
          )}

          {activeSection === 'memory' && (
            <div id="settings-memory" className="enterprise-panel flex flex-col gap-5 p-6 md:p-8">
              <div className="flex items-center gap-3 border-b border-slate-200/80 pb-4 dark:border-white/10">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <Layers3 size={18} strokeWidth={1.6} />
                </div>
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                    {isEn ? 'Conversation memory' : 'ความจำการสนทนา'}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {isEn
                      ? 'Review working notes, preferences, and saved definitions without opening Chat.'
                      : 'ดูบันทึกงาน ค่ากำหนด และนิยามที่บันทึกไว้ โดยไม่ต้องเปิด Chat'}
                  </p>
                </div>
              </div>
              <div className="flex flex-col gap-3 rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-zinc-900/45 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  {isEn
                    ? 'Opens the same memory manager used in Chat, including saved definitions.'
                    : 'เปิดตัวจัดการความจำเดียวกับใน Chat รวมนิยามที่บันทึกไว้'}
                </p>
                <button
                  type="button"
                  onClick={() => setShowMemoryPanel(true)}
                  className="btn-primary inline-flex shrink-0 items-center justify-center gap-2 px-4 py-2.5 text-sm"
                >
                  <Layers3 size={15} />
                  {isEn ? 'Manage memory' : 'จัดการความจำ'}
                </button>
              </div>
            </div>
          )}

          {activeSection === 'organization' && showOrganizationSection ? (
            <OrganizationWorkspaceSettings
              userId={user?.id}
              isEn={isEn}
              planName={plan?.name}
            />
          ) : null}

          {activeSection === 'plan' && (
            <div id="settings-plan" className="enterprise-panel p-6 flex flex-col gap-5">
              <div className="flex items-center gap-3 border-b border-slate-200/80 dark:border-white/10 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <CreditCard size={18} strokeWidth={1.6} />
                </div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {isEn ? 'Billing & Plan' : 'แผนบริการและการเรียกเก็บเงิน'}
                </h2>
              </div>

              <div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 uppercase font-medium tracking-wider">{t(m, 'settings.current_plan', 'Current plan')}</p>
                <p className="text-lg font-semibold text-slate-900 dark:text-slate-100 mt-1">{plan?.name || 'Free'} Plan</p>
                {plan?.name === 'Enterprise' && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {plan.subscription_seats} {isEn ? 'subscribed users' : 'ผู้ใช้ที่สมัครไว้'}
                  </p>
                )}
              </div>

              {plan?.name === 'Free' && (
                <button onClick={() => router.push(localePath('/pricing', routing))} className="w-full btn-primary py-3 text-sm">
                  {t(m, 'settings.upgrade_plus', 'Upgrade to Plus')}
                </button>
              )}
              {plan?.name === 'Plus' && (
                <button onClick={() => router.push(localePath('/pricing', routing))} className="w-full btn-primary py-3 text-sm">
                  {t(m, 'settings.upgrade_pro', 'Upgrade to Pro')}
                </button>
              )}

              {plan?.name !== 'Free' && (
                <button
                  onClick={handleCancel}
                  disabled={loading}
                  className="w-full text-center text-sm border border-red-200 dark:border-red-900/30 hover:bg-red-50 dark:hover:bg-red-950/20 py-3 rounded-[0.75rem] font-semibold text-red-500 hover:text-red-700 transition-colors disabled:opacity-50"
                >
                  {loading ? t(m, 'settings.canceling', 'Canceling...') : t(m, 'settings.cancel_subscription', 'Cancel Subscription')}
                </button>
              )}

              <button
                onClick={handleViewBilling}
                className="w-full text-center text-sm border border-slate-200 dark:border-white/12 hover:bg-slate-50 dark:hover:bg-zinc-800 py-3 rounded-[0.75rem] font-semibold text-slate-600 dark:text-slate-300 transition-colors"
              >
                {t(m, 'settings.view_billing', 'View Billing History')}
              </button>
            </div>
          )}

          {activeSection === 'appearance' && (
            <div id="settings-appearance" className="enterprise-panel p-6 flex flex-col gap-5">
              <div className="flex items-center gap-3 border-b border-slate-200/80 dark:border-white/10 pb-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-50 text-[#d97706] dark:bg-amber-500/10">
                  <SunMoon size={18} strokeWidth={1.6} />
                </div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                  {t(m, 'settings.appearance', 'Appearance')}
                </h2>
              </div>

              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t(m, 'settings.dark_mode', 'Dark Mode')}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t(m, 'settings.dark_desc', 'Switch the app theme for comfortable viewing.')}</p>
                </div>
                <button
                  onClick={toggleTheme}
                  className={`w-12 h-6 rounded-full relative transition-colors duration-300 focus:outline-none flex-shrink-0 ${theme === 'dark' ? 'bg-[#d97706]' : 'bg-slate-200 dark:bg-zinc-700'}`}
                >
                  <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform duration-300 ${theme === 'dark' ? 'translate-x-6' : ''}`}></div>
                </button>
              </div>

              <div className="flex items-center justify-between gap-4 border-t border-slate-200/80 pt-5 dark:border-white/10">
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {t(m, 'settings.language', 'Language')}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {t(m, 'settings.language_desc', 'Choose Thai or English for the workspace interface.')}
                  </p>
                </div>
                <LocaleSwitcher variant="dropdown" className="min-w-[12rem]" />
              </div>
            </div>
          )}
        </div>
      </div>
      </main>

      <ChatMemoryPanel
        open={showMemoryPanel}
        onClose={() => setShowMemoryPanel(false)}
        userId={user?.id}
        isEn={isEn}
      />

      {/* Image Cropper Popup (Nested Modal) */}
      {imageToCrop && (
        <div className="fixed inset-0 z-[110] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-zinc-950 w-full max-w-md rounded-2xl border border-slate-200 dark:border-white/10 overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-200 dark:border-white/10 flex justify-between items-center">
              <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t(m, 'settings.crop_title', 'Adjust image size')}</h2>
              <button onClick={() => setImageToCrop(null)} className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg transition-colors">
                <X className="w-5 h-5" strokeWidth={1.5} />
              </button>
            </div>
            
            <div className="relative bg-[#1a1a1a] dark:bg-black h-64">
              {CropperComponent ? (
                <CropperComponent
                  image={imageToCrop}
                  crop={crop}
                  zoom={zoom}
                  aspect={1}
                  onCropChange={setCrop}
                  onZoomChange={setZoom}
                  onCropComplete={onCropComplete}
                  cropShape="round"
                  showGrid={false}
                />
              ) : null}
            </div>

            <div className="p-5 bg-white dark:bg-zinc-950 border-t border-slate-200 dark:border-white/10">
              <div className="flex flex-col gap-5">
                <div className="flex items-center gap-4">
                  <span className="text-[11px] uppercase font-medium text-slate-400 tracking-wider">Zoom</span>
                  <input
                    type="range"
                    value={zoom}
                    min={1}
                    max={3}
                    step={0.1}
                    onChange={(e) => setZoom(Number(e.target.value))}
                    className="flex-1 h-1.5 bg-slate-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-[#d97706]"
                  />
                </div>
                
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setImageToCrop(null)}
                    className="px-4 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
                  >
                    {t(m, 'settings.cancel', 'Cancel')}
                  </button>
                  <button
                    onClick={handleConfirmCrop}
                    disabled={uploading}
                    className="px-5 py-2 btn-primary text-sm disabled:opacity-50"
                  >
                    {uploading ? t(m, 'settings.processing', 'Processing...') : t(m, 'settings.confirm_profile_image', 'Confirm profile image')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Success Notification Popup */}
      {showSuccess && (
        <div className="fixed top-10 left-1/2 -translate-x-1/2 z-[200]">
          <div className="bg-white dark:bg-zinc-900 border border-emerald-200 dark:border-emerald-900/40 py-3 px-5 rounded-xl flex items-center gap-3">
            <div className="w-5 h-5 bg-emerald-600 rounded-full flex items-center justify-center shrink-0">
              <Check className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
            </div>
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{successText}</span>
          </div>
        </div>
      )}

      <DeleteConfirmationModal
        isOpen={isCancelConfirmOpen}
        onClose={() => setIsCancelConfirmOpen(false)}
        onConfirm={confirmCancelSubscription}
        icon="alert"
        title={t(m, 'settings.cancel_confirm_title', 'Cancel Subscription')}
        message={t(
          m,
          'settings.cancel_confirm_desc',
          'Are you sure you want to cancel? Your storage limit and daily token quota will return to the Free plan.',
        )}
        confirmButtonText={t(m, 'settings.cancel_confirm_yes', 'Yes, Cancel')}
        cancelButtonText={t(m, 'settings.cancel_confirm_back', 'Back')}
      />
    </div>
  );
};

export default SettingsPage;
