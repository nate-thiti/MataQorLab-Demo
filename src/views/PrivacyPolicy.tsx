// @ts-nocheck
'use client';

import { useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import LegalDocumentView from '../components/LegalDocumentView';
import { PRIVACY_SECTION_ORDER } from '../content/legalSections.js';
import { buildLegalPath, PRIVACY_SECTIONS } from '../utils/dashboardRoutes.js';

const PrivacyPolicy = ({ embedded = false }) => {
  const router = useRouter();
  const { section } = useParams();
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);

  const sections = PRIVACY_SECTION_ORDER.map((id) => ({
    id,
    title: t(m, `privacy_policy.sections.${id}.title`),
    body: t(m, `privacy_policy.sections.${id}.body`),
  }));

  useEffect(() => {
    if (embedded || !section) return;
    if (!PRIVACY_SECTIONS.has(section)) {
      router.replace(buildLegalPath(routing, 'privacy'));
    }
  }, [embedded, section, router, routing]);

  useEffect(() => {
    if (embedded || !section || !PRIVACY_SECTIONS.has(section)) return;
    document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [embedded, section]);

  return (
    <LegalDocumentView
      embedded={embedded}
      title={t(m, 'privacy_policy.title', 'Privacy Policy')}
      updated={t(m, 'privacy_policy.updated', 'Last updated: June 2026')}
      sections={sections}
      activeSection={section}
      getSectionHref={
        embedded ? undefined : (sectionId) => buildLegalPath(routing, 'privacy', sectionId)
      }
      backLink={
        embedded
          ? undefined
          : {
              href: localePath('/login', routing),
              label: t(m, 'privacy_policy.back_login', 'Back to sign in'),
            }
      }
      crossLink={
        embedded
          ? undefined
          : {
              href: buildLegalPath(routing, 'terms'),
              label: t(m, 'privacy_policy.view_terms', 'View Terms of Service'),
            }
      }
      contactLabel={t(m, 'privacy_policy.contact_label', 'Privacy inquiries')}
      contactEmail={t(m, 'privacy_policy.contact_email', 'support@example.com')}
      footerNote={t(m, 'privacy_policy.footer_note', '')}
    />
  );
};

export default PrivacyPolicy;
