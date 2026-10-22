// @ts-nocheck
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { recoverInvalidBrowserSession, supabase } from '../utils/supabaseClient.js';
import HeroSection from '../components/HeroSection';
import LandingScrollExperience from '../components/marketing/LandingScrollExperience';
import FeaturesSection from '../components/FeaturesSection';
import PipelineSection from '../components/PipelineSection';
import FaqSection from '../components/FaqSection';
import BottomCtaSection from '../components/BottomCtaSection';
import MarketingLayout from '../components/marketing/MarketingLayout';
import { getMessages } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';

const LandingPage = () => {
  const router = useRouter();
  const routing = useLocaleRouting();
  const isEn = routing.locale === 'en';
  const m = getMessages(routing.locale);

  useEffect(() => {
    const checkUserSession = async () => {
      const { data: { user }, error } = await supabase.auth.getUser();
      if (await recoverInvalidBrowserSession(error)) return;
      if (user) {
        router.push(localePath('/dashboard', routing));
      }
    };
    checkUserSession();
  }, [router, routing]);

  return (
    <MarketingLayout>
      <HeroSection routing={routing} m={m} />
      <LandingScrollExperience />
      <FeaturesSection m={m} />
      <PipelineSection m={m} />
      <FaqSection m={m} isEn={isEn} />
      <BottomCtaSection routing={routing} m={m} />
    </MarketingLayout>
  );
};

export default LandingPage;
