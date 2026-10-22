// @ts-nocheck
import Link from 'next/link';
import { t } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';
import MQLogo from '../assets/MQ.svg';

const Footer = ({ routing, m, marketing = false }) => {
  const currentYear = new Date().getFullYear();

  return (
    <footer className={marketing ? 'marketing-footer py-12 px-6' : 'border-t border-slate-200/80 dark:border-slate-800/80 py-12 px-6 bg-white dark:bg-slate-900'}>
      <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8">
        <div className="md:col-span-2 space-y-3">
          <div className="flex items-center gap-2">
            <img src={MQLogo?.src || MQLogo} alt="MataQorLab Logo" className="w-8 h-8 object-contain" />
            <span className="text-base font-bold tracking-tight marketing-heading">
              MataQorLab
            </span>
          </div>
          <p className="text-xs marketing-subtext max-w-sm leading-relaxed">
            {t(m, 'landing.hero_desc')}
          </p>
          <p className="text-xs marketing-subtext opacity-75">
            © {currentYear} MataQorLab. {t(m, 'navigation.all_rights_reserved', 'All rights reserved.')}
          </p>
        </div>

        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider marketing-footer-title">{t(m, 'navigation.product', 'Product')}</h4>
          <div className="flex flex-col gap-2 text-xs font-medium">
            <Link href={localePath('/platform', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.platform', 'Platform')}
            </Link>
            <Link href={localePath('/solutions', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.solutions', 'Solutions')}
            </Link>
            <Link href={localePath('/documentation', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.documentation', 'Documentation')}
            </Link>
            <Link href={localePath('/pricing', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.pricing', 'Pricing')}
            </Link>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider marketing-footer-title">{t(m, 'navigation.legal', 'Legal')}</h4>
          <div className="flex flex-col gap-2 text-xs font-medium">
            <Link href={localePath('/privacy-policy', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.privacy_policy', 'Privacy Policy')}
            </Link>
            <Link href={localePath('/terms-of-service', routing)} className="marketing-footer-link transition-colors">
              {t(m, 'navigation.terms_of_service', 'Terms of Service')}
            </Link>
            <a href="mailto:support@mataqorlab.com" className="marketing-footer-link transition-colors">
              {t(m, 'navigation.contact_us', 'Contact Us')}
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
