// @ts-nocheck
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Cookie } from '@/components/icons';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { buildLegalPath } from '../utils/dashboardRoutes.js';
import { getMessages, t } from '../utils/i18n.js';

const CookieConsent = () => {
  const [isVisible, setIsVisible] = useState(false);
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);
  const privacyHref = buildLegalPath(routing, 'privacy', 'cookies');

  useEffect(() => {
    setIsVisible(!localStorage.getItem('cookie_consent_accepted'));
  }, []);

  const handleAccept = () => {
    localStorage.setItem('cookie_consent_accepted', 'true');
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="cookie-consent-title"
      className="fixed bottom-4 inset-x-4 z-50 mx-auto max-w-lg rounded-2xl border border-[#e5dec9] bg-[#ffffff] p-5 shadow-xl md:bottom-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#fff7ed] text-[#d97706]">
            <Cookie className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <h3
              id="cookie-consent-title"
              className="text-lg font-serif font-semibold text-[#1a1a1a]"
            >
              {t(m, 'cookie.title')}
            </h3>
            <p className="mt-1 text-sm leading-relaxed text-[#5a5542]">
              {t(m, 'cookie.desc')}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-[#5a5542]">
              {t(m, 'cookie.read_prefix')}{' '}
              <Link
                href={privacyHref}
                className="font-medium text-[#d97706] underline-offset-2 hover:underline"
              >
                {t(m, 'cookie.read_link')}
              </Link>
              .
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleAccept}
            className="rounded-full bg-[#d97706] px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-[#b45309]"
          >
            {t(m, 'cookie.accept')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieConsent;
