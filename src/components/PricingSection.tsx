// @ts-nocheck
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '../utils/supabaseClient.js';
import { t } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';
import { calculateEnterpriseMonthlyPrice } from '../utils/enterprisePricing.js';
import MarketingButton from './marketing/MarketingButton';
import AppBanner from './AppBanner';
import PlanAudienceSwitch from './PlanAudienceSwitch';
import {
  BarChart3,
  CheckCircle2,
  Clock3,
  CloudUpload,
  Database,
  FilePlus2,
  Globe,
  Lightbulb,
  Network,
  Server,
} from '@/components/icons';

const PricingSection = ({ m, routing, hideHeader = false }) => {
  const [plans, setPlans] = useState<any[]>([]);
  const [user, setUser] = useState<any>(null);
  const [currentPlanId, setCurrentPlanId] = useState<any>(null);
  const [audience, setAudience] = useState('individual');
  const [enterpriseSeats, setEnterpriseSeats] = useState(2);
  const [enterpriseOrganizationName, setEnterpriseOrganizationName] = useState('');
  const [loadingAction, setLoadingAction] = useState(false);
  const [banner, setBanner] = useState<any>(null);
  const router = useRouter();

  useEffect(() => {
    const fetchPlans = async () => {
      const { data, error } = await supabase.from('plans').select('*').order('price_monthly', { ascending: true });
      if (data) setPlans(data);
      if (error) console.error('Error fetching plans for landing page:', error);
    };
    
    const checkUser = async () => {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        if (user) {
          setUser(user);
          const { data: profile } = await supabase
            .from('profiles')
            .select('plan_id')
            .eq('id', user.id)
            .maybeSingle();
          if (profile) {
            setCurrentPlanId(profile.plan_id);
          }
        }
      } catch (err: any) {
        console.error('Error fetching user for pricing page:', err);
      }
    };

    fetchPlans();
    checkUser();
  }, []);

  const handleSelectPlan = async (selectedPlan) => {
    const isEnterprise = selectedPlan.name?.toLowerCase() === 'enterprise';
    const seats = isEnterprise ? Math.min(500, Math.max(2, enterpriseSeats)) : 1;
    const organizationName = enterpriseOrganizationName.trim();
    if (isEnterprise && (organizationName.length < 2 || organizationName.length > 160)) {
      setBanner({
        type: 'error',
        message: routing.locale === 'en'
          ? 'Enter an organization name between 2 and 160 characters.'
          : 'กรอกชื่อองค์กรระหว่าง 2–160 ตัวอักษร',
      });
      return;
    }
    if (!user) {
      sessionStorage.setItem('matqor_pending_plan_id', selectedPlan.id);
      sessionStorage.setItem('matqor_pending_plan_seats', String(seats));
      localStorage.setItem('matqor_pending_plan_id', selectedPlan.id);
      localStorage.setItem('matqor_pending_plan_seats', String(seats));
      localStorage.setItem('matqor_registration_audience', isEnterprise ? 'business' : 'individual');
      if (isEnterprise) {
        localStorage.setItem('matqor_pending_organization_name', organizationName);
      }
      router.push(localePath('/register', routing));
      return;
    }

    if (selectedPlan.id === currentPlanId) {
      return;
    }

    setLoadingAction(true);
    setBanner(null);
    try {
      if (selectedPlan.price_monthly === 0) {
        const { handleCancelSubscription } = await import('../utils/stripe.js');
        await handleCancelSubscription({ user_id: user.id });
        setBanner({
          type: 'success',
          message: routing.locale === 'en'
            ? 'Successfully downgraded to Free plan!'
            : 'เปลี่ยนเป็นแพ็กเกจ Free สำเร็จ!',
        });
        setTimeout(() => router.push(localePath('/dashboard', routing)), 1200);
      } else {
        const { handleStripeCheckout } = await import('../utils/stripe.js');
        await handleStripeCheckout({
          user_id: user.id,
          plan_id: selectedPlan.id,
          seats,
          organization_name: isEnterprise ? organizationName : null,
        });
      }
    } catch (err: any) {
      console.error("Error processing plan change:", err);
      setBanner({
        type: 'error',
        message: err.message || (routing.locale === 'en'
          ? 'Failed to change plan. Please try again.'
          : 'เกิดข้อผิดพลาดในการเปลี่ยนแผนบริการ กรุณาลองใหม่อีกครั้ง'),
      });
    } finally {
      setLoadingAction(false);
    }
  };

  // ข้อมูลฟีเจอร์สำหรับหน้าราคาจำแนกตามแผนบริการ (รองรับ 2 ภาษาผ่าน i18n)
  const getPlanFeatures = (planName) => {
    switch (planName) {
      case 'Free':
        return [
          { text: t(m, 'landing.pricing_features.free.tokens', "200,000 tokens (Refresh 2 days)"), icon: "check" },
          { text: t(m, 'landing.pricing_features.free.reasoning', "Basic reasoning capabilities"), icon: "check" },
          { text: t(m, 'landing.pricing_features.free.upload', "1MB upload space"), icon: "document" },
          { text: t(m, 'landing.pricing_features.free.formats', "Excel, CSV, JSON analysis"), icon: "check" },
        ];
      case 'Plus':
        return [
          { text: t(m, 'landing.pricing_features.plus.tokens', "400,000 tokens (Daily Refresh)"), icon: "check" },
          { text: t(m, 'landing.pricing_features.plus.web_search', "Auto Web Search"), icon: "globe" },
          { text: t(m, 'landing.pricing_features.plus.reasoning', "Complex reasoning model"), icon: "lightbulb" },
          { text: t(m, 'landing.pricing_features.plus.upload', "200MB upload space"), icon: "cloud" },
          { text: t(m, 'landing.pricing_features.plus.formats', "Excel, CSV, JSON, PARQUET"), icon: "check" },
          { text: t(m, 'landing.pricing_features.plus.conn', "External API Connection"), icon: "network" },
        ];
      case 'Pro':
        return [
          { text: t(m, 'landing.pricing_features.pro.tokens', "1,000,000 tokens (Daily Refresh)"), icon: "check" },
          { text: t(m, 'landing.pricing_features.pro.weekly_limit', "No weekly limit"), icon: "clock" },
          { text: t(m, 'landing.pricing_features.pro.web_search', "Auto Web Search"), icon: "globe" },
          { text: t(m, 'landing.pricing_features.pro.reasoning', "Maximum complex reasoning"), icon: "star" },
          { text: t(m, 'landing.pricing_features.pro.upload', "500MB upload space"), icon: "database" },
          { text: t(m, 'landing.pricing_features.pro.formats', "Excel, CSV, JSON, PARQUET"), icon: "check" },
          { text: t(m, 'landing.pricing_features.pro.conapi', "External API Connector"), icon: "network" },
          { text: t(m, 'landing.pricing_features.pro.conn', "External SQL Server Connection"), icon: "server" },
        ];
      case 'Enterprise':
        return [
          { text: t(m, 'landing.pricing_features.enterprise.tokens', "2,000,000 tokens (Daily Refresh)"), icon: "check" },
          { text: t(m, 'landing.pricing_features.enterprise.reasoning', "Maximum complex reasoning"), icon: "star" },
          { text: t(m, 'landing.pricing_features.enterprise.upload', "2GB upload space"), icon: "database" },
          { text: t(m, 'landing.pricing_features.enterprise.formats', "All supported data connectors"), icon: "network" },
          { text: t(m, 'landing.pricing_features.enterprise.sso', "Organization workspace and governed memory"), icon: "server" },
          { text: t(m, 'landing.pricing_features.enterprise.support', "Priority support"), icon: "check" },
        ];
      default:
        return [];
    }
  };

  const renderIcon = (iconName) => {
    const classes = "w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0";
    const props = { className: classes, strokeWidth: 1.5 };
    switch (iconName) {
      case 'check':
        return <CheckCircle2 {...props} />;
      case 'globe':
        return <Globe {...props} />;
      case 'lightbulb':
        return <Lightbulb {...props} />;
      case 'star':
        return <Lightbulb {...props} />;
      case 'clock':
        return <Clock3 {...props} />;
      case 'document':
        return <FilePlus2 {...props} />;
      case 'cloud':
        return <CloudUpload {...props} />;
      case 'database':
        return <Database {...props} />;
      case 'network':
        return <Network {...props} />;
      case 'server':
        return <Server {...props} />;
      default:
        return null;
    }
  };

  const comparisonRows = [
    { key: 'row_tokens', free: 'val_free_tokens', plus: 'val_plus_tokens', pro: 'val_pro_tokens', enterprise: 'val_ent_tokens' },
    { key: 'row_upload', free: 'val_free_upload', plus: 'val_plus_upload', pro: 'val_pro_upload', enterprise: 'val_ent_upload' },
    { key: 'row_parquet', free: 'val_no', plus: 'val_yes', pro: 'val_yes', enterprise: 'val_yes' },
    { key: 'row_api', free: 'val_no', plus: 'val_yes', pro: 'val_yes', enterprise: 'val_yes' },
    { key: 'row_sql', free: 'val_no', plus: 'val_no', pro: 'val_yes', enterprise: 'val_yes' },
    { key: 'row_priority', free: 'val_no', plus: 'val_yes', pro: 'val_yes', enterprise: 'val_yes' },
  ];
  const visiblePlans = plans.filter((plan) => (
    audience === 'business'
      ? plan.name === 'Enterprise'
      : plan.name !== 'Enterprise'
  ));

  return (
    <section className="py-16 w-full px-6 marketing-section-divider">
      <div className={`max-w-4xl mx-auto text-center ${hideHeader ? 'mb-8' : 'mb-14'} space-y-4`} data-reveal>
        {!hideHeader && <>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            {t(m, 'landing.pricing_title_page')}
          </h2>
          <p className="text-sm md:text-base marketing-subtext max-w-2xl mx-auto leading-relaxed">
            {t(m, 'landing.pricing_desc_page')}
          </p>
        </>}
        {banner && (
          <div className="max-w-xl mx-auto text-left">
            <AppBanner type={banner.type} message={banner.message} />
          </div>
        )}
        <PlanAudienceSwitch
          value={audience}
          onChange={(nextAudience) => {
            setAudience(nextAudience);
            setBanner(null);
          }}
          isEn={routing.locale === 'en'}
        />
        <p className="mx-auto max-w-2xl text-sm marketing-subtext">
          {audience === 'business'
            ? (routing.locale === 'en'
              ? 'One governed organization with shared workspaces, company memory, team roles and billing by active seats.'
              : 'หนึ่งองค์กรที่กำกับได้ พร้อม Workspace ร่วม, Company Memory, Team Role และคิดค่าบริการตามจำนวน Seats')
            : (routing.locale === 'en'
              ? 'Personal plans for independent analysis, from essential workflows to advanced connectors.'
              : 'แผนส่วนบุคคลสำหรับงานวิเคราะห์ ตั้งแต่งานพื้นฐานถึง Connector ขั้นสูง')}
        </p>
      </div>

      <div className={`mx-auto grid grid-cols-1 gap-6 items-stretch mb-16 ${
        audience === 'business'
          ? 'max-w-2xl'
          : 'max-w-6xl md:grid-cols-2 xl:grid-cols-3'
      }`}>
        {visiblePlans.map((plan) => {
          const isFree = plan.price_monthly === 0;
          const isPopular = plan.name === 'Plus';
          const isEnterprise = plan.name === 'Enterprise';
          const enterprisePricing = isEnterprise
            ? calculateEnterpriseMonthlyPrice(plan, enterpriseSeats)
            : null;
          const features = getPlanFeatures(plan.name);
          const isCurrentPlan = plan.id === currentPlanId;

          return (
            <div
              key={plan.id}
              className={`marketing-card marketing-card-hover p-6 flex flex-col justify-between relative ${isPopular ? 'ring-2 ring-amber-600/40 !pt-10' : ''}`}
              data-reveal
              data-spotlight
            >
              {isPopular && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 bg-amber-600 text-white text-[10px] font-bold px-5 py-1 rounded-b-md uppercase tracking-wider whitespace-nowrap">
                  {routing.locale === 'en' ? 'Popular' : 'ยอดนิยม'}
                </div>
              )}

              <div className="space-y-5 text-left">
                <div className="inline-block bg-slate-100 dark:bg-slate-800 text-slate-500 text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded">
                  {plan.name}
                </div>

                <div className="space-y-1">
                  <div className="text-3xl font-extrabold tabular-nums marketing-metric-value !text-3xl">
                    {isFree ? '0 USD' : `${plan.price_monthly} USD`}
                  </div>
                  <div className="text-xs marketing-subtext font-mono">
                    {isEnterprise
                      ? (routing.locale === 'en' ? '/organization/month' : '/องค์กร/เดือน')
                      : `/${t(m, 'landing.per_month')}`}
                  </div>
                </div>

                {isEnterprise && (
                  <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
                    <p className="text-xs marketing-subtext">
                      {routing.locale === 'en'
                        ? `${enterprisePricing.includedSeats} seats included; ${enterprisePricing.additionalSeatPrice} USD/month per additional seat`
                        : `รวม ${enterprisePricing.includedSeats} Seats; Seat เพิ่ม ${enterprisePricing.additionalSeatPrice} USD/เดือน`}
                    </p>
                    <label htmlFor="enterprise-pricing-organization" className="text-xs font-semibold marketing-subtext">
                      {routing.locale === 'en' ? 'Organization name' : 'ชื่อองค์กร'}
                    </label>
                    <input
                      id="enterprise-pricing-organization"
                      type="text"
                      minLength={2}
                      maxLength={160}
                      value={enterpriseOrganizationName}
                      onChange={(event) => setEnterpriseOrganizationName(event.target.value)}
                      placeholder={routing.locale === 'en' ? 'Acme Analytics' : 'บริษัท ตัวอย่าง จำกัด'}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                    />
                    <label htmlFor="enterprise-pricing-seats" className="text-xs font-semibold marketing-subtext">
                      {routing.locale === 'en' ? 'Team size (minimum 2)' : 'จำนวนผู้ใช้ (ขั้นต่ำ 2)'}
                    </label>
                    <input
                      id="enterprise-pricing-seats"
                      type="number"
                      min={2}
                      max={500}
                      value={enterpriseSeats}
                      onChange={(event) => setEnterpriseSeats(
                        Math.min(500, Math.max(2, Number(event.target.value) || 2))
                      )}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                    />
                    <p className="text-xs marketing-subtext">
                      {routing.locale === 'en' ? 'Total' : 'รวม'}:{' '}
                      <strong>{enterprisePricing.monthlyTotal} USD/{routing.locale === 'en' ? 'month' : 'เดือน'}</strong>
                    </p>
                  </div>
                )}

                <hr className="border-slate-100 dark:border-slate-700" />

                <ul className="space-y-2">
                  {features.map((feat, idx) => (
                    <li key={idx} className="flex items-center gap-2 text-sm marketing-subtext">
                      {renderIcon(feat.icon)}
                      <span>{feat.text}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="mt-6">
                {isCurrentPlan ? (
                  <button disabled className="w-full py-3 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed">
                    {routing.locale === 'en' ? 'Current Plan' : 'แพลนปัจจุบัน'}
                  </button>
                ) : (
                  <MarketingButton
                    variant={isFree ? 'primary' : 'secondary'}
                    type="button"
                    onClick={() => handleSelectPlan(plan)}
                    disabled={loadingAction}
                    className="w-full py-3 text-xs"
                  >
                    {isFree
                      ? t(m, 'landing.start_free')
                      : routing.locale === 'en'
                        ? `Subscribe ${plan.name}`
                        : `สมัครสมาชิก ${plan.name}`}
                  </MarketingButton>
                )}
              </div>
            </div>
          );
        })}

      </div>

      {/* Individual feature comparison table */}
      {audience === 'individual' && (
      <div className="max-w-6xl mx-auto mb-16" data-reveal>
        <h3 className="text-xl font-bold mb-6 text-center">
          {t(m, 'landing.comparison.title')}
        </h3>
        <div className="marketing-card overflow-x-auto">
          <table className="w-full text-sm text-left min-w-[640px]">
            <thead>
              <tr className="border-b border-slate-200/80 dark:border-slate-600/50">
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider marketing-subtext">
                  {t(m, 'landing.comparison.feature_col')}
                </th>
                {['Free', 'Plus', 'Pro'].map((col) => (
                  <th key={col} className="px-4 py-3 text-xs font-bold">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(({ key, free, plus, pro }) => (
                <tr key={key} className="border-b border-slate-100 dark:border-slate-700/80 last:border-0">
                  <td className="px-4 py-3 text-sm font-medium marketing-subtext">{t(m, `landing.comparison.${key}`)}</td>
                  <td className="px-4 py-3 text-sm">{t(m, `landing.comparison.${free}`)}</td>
                  <td className="px-4 py-3 text-sm">{t(m, `landing.comparison.${plus}`)}</td>
                  <td className="px-4 py-3 text-sm">{t(m, `landing.comparison.${pro}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      )}

      <div className="max-w-2xl mx-auto text-left" data-reveal>
        <div className="marketing-card p-6 flex gap-4 items-start" data-spotlight>
          <div className="w-10 h-10 rounded-lg bg-amber-600/10 flex items-center justify-center text-amber-600 shrink-0">
            <BarChart3 className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <div className="space-y-1.5">
            <h4 className="text-base font-bold">{t(m, 'landing.analysis_chat_title', 'Analysis Chat')}</h4>
            <p className="text-sm marketing-subtext leading-relaxed">
              {routing.locale === 'en'
                ? 'Deterministic analysis across the complete 16-stage data lifecycle, with large uploads, SQL connections, API integration, monitoring, audit, and cost control.'
                : 'วิเคราะห์แบบ deterministic ตลอด lifecycle ข้อมูล 16 ขั้น รองรับไฟล์ขนาดใหญ่ SQL, API, monitoring, audit และ cost control'}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PricingSection;
