// @ts-nocheck
'use client';

import MarketingLayout from '../components/marketing/MarketingLayout';
import PricingSection from '../components/PricingSection';
import { getMessages } from '../utils/i18n.js';
import { useLocaleRouting } from '../context/LocaleRoutingContext';

const PricingPage = () => {
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);
  const isEn = routing.locale === 'en';

  return (
    <MarketingLayout mainClassName="marketing-page-shell">
      <section className="marketing-page-hero">
        <div className="max-w-6xl mx-auto relative z-10" data-reveal>
          <div className="marketing-page-kicker mb-6">{isEn ? 'PLANS & OPERATING CAPACITY' : 'แผนบริการและขีดความสามารถ'}</div>
          <h1 className="marketing-heading text-4xl md:text-6xl font-bold tracking-tight leading-[1.08] max-w-4xl">
            {isEn ? 'Scale analytics without losing control.' : 'ขยายงานวิเคราะห์ โดยไม่สูญเสียการควบคุม'}
          </h1>
          <p className="marketing-subtext text-base md:text-lg leading-relaxed max-w-2xl mt-7">
            {isEn
              ? 'Every plan runs on the same governed lifecycle. Choose the capacity, connectivity, and operational controls appropriate for your team.'
              : 'ทุกแผนทำงานบน lifecycle ที่กำกับแบบเดียวกัน เลือก capacity การเชื่อมต่อ และระดับการควบคุมที่เหมาะกับทีมของคุณ'}
          </p>
        </div>
      </section>
      <PricingSection m={m} routing={routing} hideHeader />
    </MarketingLayout>
  );
};

export default PricingPage;
