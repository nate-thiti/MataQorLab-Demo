// @ts-nocheck
import Link from 'next/link';
import { ArrowLeft, ChevronRight } from '@/components/icons';

const paragraphClass = (embedded) =>
  embedded
    ? 'text-sm text-slate-600 dark:text-slate-300 leading-relaxed'
    : 'text-base text-slate-600 dark:text-slate-300 leading-relaxed';

const headingClass = (embedded) =>
  embedded
    ? 'text-base font-semibold text-slate-900 dark:text-slate-100 scroll-mt-4'
    : 'text-lg font-semibold text-slate-900 dark:text-slate-100 scroll-mt-24';

const renderBody = (body, embedded) => {
  const parts = String(body || '')
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  return parts.map((paragraph, index) => (
    <p key={index} className={`${paragraphClass(embedded)}${index > 0 ? ' mt-4' : ''}`}>
      {paragraph}
    </p>
  ));
};

const LegalDocumentView = ({
  title,
  updated,
  sections,
  embedded = false,
  backLink,
  crossLink,
  contactLabel,
  contactEmail,
  footerNote,
  getSectionHref,
  activeSection,
}) => {
  const content = (
    <>
      <header className={embedded ? 'pb-6 mb-6 border-b border-slate-200 dark:border-slate-600' : 'pb-8 mb-10 border-b border-slate-200 dark:border-slate-600'}>
        <h1
          className={
            embedded
              ? 'text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight'
              : 'text-3xl md:text-4xl font-bold text-slate-900 dark:text-slate-100 tracking-tight'
          }
        >
          {title}
        </h1>
        <p className="mt-2 text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {updated}
        </p>
      </header>

      <div className={embedded ? 'space-y-8' : 'space-y-0 divide-y divide-slate-200 dark:divide-slate-700'}>
        {sections.map((section, index) => (
          <section
            key={section.id}
            id={embedded ? undefined : section.id}
            className={[
              !embedded && !section.highlight ? 'py-10 first:pt-0 last:pb-0' : '',
              embedded && index > 0 ? 'pt-8 border-t border-slate-200 dark:border-slate-700' : '',
              section.highlight
                ? 'rounded-xl border border-amber-200/80 bg-amber-50/80 p-5 dark:border-amber-800/60 dark:bg-amber-950/30'
                : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <h2
              className={`${headingClass(embedded)}${
                section.highlight ? ' text-amber-900 dark:text-amber-200' : ''
              } mb-3`}
            >
              {section.title}
            </h2>
            {renderBody(section.body, embedded)}
          </section>
        ))}
      </div>

      {!embedded && crossLink && (
        <div className="mt-10 pt-8 border-t border-slate-200 dark:border-slate-600">
          <Link
            href={crossLink.href}
            className="inline-flex items-center gap-1 text-sm font-medium text-[#d97706] hover:text-[#b45309] transition-colors"
          >
            {crossLink.label}
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      )}

      {!embedded && (contactLabel || footerNote) && (
        <footer className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-600 space-y-2">
          {contactLabel && contactEmail && (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {contactLabel}:{' '}
              <a href={`mailto:${contactEmail}`} className="text-[#d97706] hover:underline">
                {contactEmail}
              </a>
            </p>
          )}
          {footerNote && (
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{footerNote}</p>
          )}
        </footer>
      )}
    </>
  );

  if (embedded) {
    return <div className="font-sans text-slate-900 dark:text-slate-100">{content}</div>;
  }

  return (
    <div className="min-h-screen bg-[#fdfcfa] dark:bg-slate-950 bg-[radial-gradient(#e5e7eb_1.5px,transparent_1.5px)] dark:bg-[radial-gradient(#484854_1.5px,transparent_1.5px)] [background-size:24px_24px] font-sans text-slate-900 dark:text-slate-100">
      <div className="max-w-6xl mx-auto px-6 py-10 md:py-14">
        {backLink && (
          <Link
            href={backLink.href}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-[#d97706] transition-colors mb-8"
          >
            <ArrowLeft className="w-4 h-4" />
            {backLink.label}
          </Link>
        )}

        <div className="grid lg:grid-cols-[220px_minmax(0,1fr)] gap-8 lg:gap-12 items-start">
          <nav className="hidden lg:block sticky top-8 enterprise-panel p-4 border-b-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3 pb-3 border-b border-slate-200 dark:border-slate-700">
              {title}
            </p>
            <ul className="space-y-0.5 divide-y divide-slate-100 dark:divide-slate-700">
              {sections.map((section) => (
                <li key={section.id}>
                  {getSectionHref ? (
                    <Link
                      href={getSectionHref(section.id)}
                      className={`block text-sm py-2 transition-colors leading-snug ${
                        activeSection === section.id
                          ? 'text-[#d97706] font-medium'
                          : 'text-slate-600 dark:text-slate-300 hover:text-[#d97706]'
                      }`}
                    >
                      {section.title.replace(/^\d+\.\s*/, '')}
                    </Link>
                  ) : (
                    <a
                      href={`#${section.id}`}
                      className="block text-sm text-slate-600 dark:text-slate-300 hover:text-[#d97706] py-2 transition-colors leading-snug"
                    >
                      {section.title.replace(/^\d+\.\s*/, '')}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </nav>

          <div className="enterprise-panel p-8 md:p-12">{content}</div>
        </div>
      </div>
    </div>
  );
};

export default LegalDocumentView;
