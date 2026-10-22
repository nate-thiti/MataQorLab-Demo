// @ts-nocheck
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { t } from '../utils/i18n.js';
import { localePath } from '../utils/locale.js';
import MQLogo from '../assets/MQ.svg';
import MarketingButton from './marketing/MarketingButton';
import LocaleSwitcher from './LocaleSwitcher';

const Navbar = ({ isScrolled, homePath, routing, m, marketing = false }) => {
  const pathname = usePathname();
  const isPlatformActive = pathname.endsWith('/platform');
  const isSolutionsActive = pathname.endsWith('/solutions');
  const isDocumentationActive = pathname.endsWith('/documentation');
  const isPricingActive = pathname.endsWith('/pricing');
  const isLoginActive = pathname.endsWith('/login');

  const linkClass = (active) =>
    `text-sm font-medium transition-colors pb-0.5 marketing-nav-link ${
      active ? 'marketing-nav-link-active border-b-2 border-amber-600 font-semibold' : ''
    }`;

  return (
    <nav
      className={`marketing-nav ${isScrolled ? 'marketing-nav-scrolled' : ''} ${
        marketing ? '' : 'marketing-nav-app'
      }`}
    >
      <div className="marketing-nav-inner max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        <Link href={homePath} className="flex items-center gap-2 shrink-0">
          <img
            src={MQLogo?.src || MQLogo}
            alt="MataQorLab Logo"
            className="w-8 h-8 object-contain"
          />
          <span className="text-base font-bold tracking-tight marketing-heading">
            MataQorLab
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-8">
          <Link href={localePath('/platform', routing)} className={linkClass(isPlatformActive)}>
            {t(m, 'navigation.platform', 'Platform')}
          </Link>
          <Link href={localePath('/solutions', routing)} className={linkClass(isSolutionsActive)}>
            {t(m, 'navigation.solutions', 'Solutions')}
          </Link>
          <Link href={localePath('/documentation', routing)} className={linkClass(isDocumentationActive)}>
            {t(m, 'navigation.documentation', 'Documentation')}
          </Link>
          <Link href={localePath('/pricing', routing)} className={linkClass(isPricingActive)}>
            {t(m, 'navigation.pricing', 'Pricing')}
          </Link>
        </div>

        <div className="flex items-center gap-4">
          <LocaleSwitcher compact />
          <Link href={localePath('/login', routing)} className={linkClass(isLoginActive)}>
            {t(m, 'landing.login')}
          </Link>
          <MarketingButton
            variant="primary"
            to={localePath('/register', routing)}
            className="hidden px-4 py-2 text-xs sm:inline-flex"
          >
            {t(m, 'navigation.get_started', 'Get Started')}
          </MarketingButton>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
