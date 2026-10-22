// @ts-nocheck
import { t } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';
import MarketingButton from './marketing/MarketingButton';

const BottomCtaSection = ({ routing, m }) => {
  return (
    <section className="py-20 w-full px-6 marketing-bottom-cta">
      <div className="max-w-2xl mx-auto text-center space-y-6 marketing-bottom-cta-inner">
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
          {t(m, 'landing.bottom_title')}
        </h2>
        <p className="marketing-subtext text-sm md:text-base leading-relaxed max-w-lg mx-auto">
          {t(m, 'landing.bottom_desc')}
        </p>
        <div className="pt-2">
          <MarketingButton
            variant="primary"
            to={localePath('/register', routing)}
            className="px-10 py-3.5 text-sm"
          >
            {t(m, 'landing.start_free')}
          </MarketingButton>
        </div>
      </div>
    </section>
  );
};

export default BottomCtaSection;
