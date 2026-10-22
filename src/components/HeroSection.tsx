// @ts-nocheck
import { t } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';
import TrustBar from './marketing/TrustBar';
import MarketingButton from './marketing/MarketingButton';
import HeroParticleCanvas from './marketing/HeroParticleCanvas';

const HeroSection = ({ routing, m }) => {
  const trustItems = [
    { icon: 'lock', label: t(m, 'landing.trust.item1') },
    { icon: 'shield', label: t(m, 'landing.trust.item2') },
    { icon: 'server', label: t(m, 'landing.trust.item3') },
    { icon: 'chart', label: t(m, 'landing.trust.item4') },
  ];

  return (
    <>
      <section className="marketing-hero relative overflow-hidden flex items-center">
        <HeroParticleCanvas />

        <div className="relative z-10 w-full max-w-6xl mx-auto px-6 pt-24 pb-14 lg:pt-20 lg:pb-16">
          <div className="lg:grid lg:grid-cols-2 lg:gap-12 lg:items-center">
            <div className="text-center lg:text-left space-y-8">
              <h1 className="hero-content-reveal hero-content-reveal-1 text-4xl md:text-5xl xl:text-6xl font-bold leading-tight tracking-tight">
                {t(m, 'landing.hero_title_prefix')}{' '}
                <span className="marketing-accent">{t(m, 'landing.hero_title_emphasis')}</span>
                {t(m, 'landing.hero_title_suffix') ? ` ${t(m, 'landing.hero_title_suffix')}` : ''}
              </h1>

              <p className="hero-content-reveal hero-content-reveal-2 text-base md:text-lg marketing-subtext max-w-2xl mx-auto lg:mx-0 leading-relaxed">
                {t(m, 'landing.hero_desc')}
              </p>

              <div className="hero-content-reveal hero-content-reveal-3 flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-3">
                <MarketingButton
                  variant="primary"
                  to={localePath('/register', routing)}
                  className="w-full sm:w-auto px-8 py-3.5 text-sm"
                >
                  {t(m, 'landing.start_free')}
                </MarketingButton>
                <MarketingButton
                  variant="secondary"
                  to={localePath('/platform', routing)}
                  className="w-full sm:w-auto px-8 py-3.5 text-sm"
                >
                  {t(m, 'landing.hero_cta_secondary')}
                </MarketingButton>
              </div>

              <div className="hero-content-reveal hero-content-reveal-4 hero-proof-row">
                <div><strong>16</strong><span>{routing.locale === 'th' ? 'ขั้นตอน lifecycle' : 'lifecycle stages'}</span></div>
                <div><strong>&lt;2s</strong><span>{routing.locale === 'th' ? 'ตอบกลับเฉลี่ย' : 'avg. response'}</span></div>
                <div><strong>100%</strong><span>deterministic</span></div>
              </div>
            </div>

            <div className="min-h-[120px] sm:min-h-[200px] lg:min-h-[500px]" aria-hidden="true" />
          </div>
        </div>

        <div className="hero-scroll-invitation" aria-hidden="true">
          <span>{routing.locale === 'th' ? 'เลื่อนเพื่อสำรวจระบบ' : 'Scroll to explore the system'}</span>
          <i><b /></i>
        </div>
      </section>

      <TrustBar title={t(m, 'landing.trust.title')} items={trustItems} />
    </>
  );
};

export default HeroSection;
