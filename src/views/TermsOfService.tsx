// @ts-nocheck
'use client';

import { useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';
import { getMessages, t } from '../utils/i18n.js';
import LegalDocumentView from '../components/LegalDocumentView';
import { TERMS_HIGHLIGHT_SECTIONS, TERMS_SECTION_ORDER } from '../content/legalSections.js';
import { buildLegalPath, TERMS_SECTIONS } from '../utils/dashboardRoutes.js';

const TermsOfService = ({ embedded = false }) => {
  const router = useRouter();
  const { section } = useParams();
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);

  const sections = TERMS_SECTION_ORDER.map((id) => ({
    id,
    title: t(m, `terms_of_service.sections.${id}.title`),
    body: t(m, `terms_of_service.sections.${id}.body`),
    highlight: TERMS_HIGHLIGHT_SECTIONS.has(id),
  }));

  useEffect(() => {
    if (embedded || !section) return;
    if (!TERMS_SECTIONS.has(section)) {
      router.replace(buildLegalPath(routing, 'terms'));
    }
  }, [embedded, section, router, routing]);

  useEffect(() => {
    if (embedded || !section || !TERMS_SECTIONS.has(section)) return;
    document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [embedded, section]);

  return (
    <LegalDocumentView
      embedded={embedded}
      title={t(m, 'terms_of_service.title', 'Terms of Service')}
      updated={t(m, 'terms_of_service.updated', 'Effective date: June 2026')}
      sections={sections}
      activeSection={section}
      getSectionHref={
        embedded ? undefined : (sectionId) => buildLegalPath(routing, 'terms', sectionId)
      }
      backLink={
        embedded
          ? undefined
          : {
              href: localePath('/login', routing),
              label: t(m, 'terms_of_service.back_login', 'Back to sign in'),
            }
      }
      crossLink={
        embedded
          ? undefined
          : {
              href: buildLegalPath(routing, 'privacy'),
              label: t(m, 'terms_of_service.view_privacy', 'View Privacy Policy'),
            }
      }
      contactLabel={t(m, 'terms_of_service.contact_label', 'Legal inquiries')}
      contactEmail={t(m, 'terms_of_service.contact_email', 'support@example.com')}
      footerNote={t(m, 'terms_of_service.footer_note', '')}
    />
  );
};

export default TermsOfService;
