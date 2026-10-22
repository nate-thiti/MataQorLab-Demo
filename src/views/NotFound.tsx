// @ts-nocheck
'use client';

import Link from 'next/link';
import { ArrowLeft, Database, SearchX } from '@/components/icons';
import MarketingLayout from '../components/marketing/MarketingLayout';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { getMessages, t } from '../utils/i18n.js';

const NotFound = () => {
  const routing = useLocaleRouting();
  const m = getMessages(routing.locale);
  const homePath = routing.localePrefix || '/';

  return (
    <MarketingLayout mainClassName="marketing-page-shell">
      <section className="not-found-system px-6 min-h-[78vh] flex items-center">
        <div className="max-w-6xl mx-auto w-full grid lg:grid-cols-2 gap-14 items-center">
          <div data-reveal>
            <div className="marketing-page-kicker mb-6">SYSTEM ROUTE EXCEPTION</div>
            <div className="flex items-end gap-5 mb-6">
              <h1 className="text-7xl md:text-9xl font-bold tracking-[-.08em] marketing-heading">404</h1>
              <span className="font-mono text-[10px] text-rose-600 mb-4 px-2 py-1 border border-rose-200 bg-rose-50 dark:bg-rose-950/20 dark:border-rose-900 rounded">ROUTE_NOT_FOUND</span>
            </div>
            <h2 className="marketing-heading text-2xl md:text-3xl font-bold">
              {t(m, 'not_found.title', 'Page Not Found')}
            </h2>
            <p className="marketing-subtext max-w-lg mt-4 leading-relaxed">
              {t(m, 'not_found.desc', 'The requested page may have moved or no longer exists.')}
            </p>
            <Link href={homePath} className="marketing-btn marketing-btn-primary inline-flex items-center gap-2 px-6 py-3 mt-8 rounded-lg text-sm font-semibold">
              <ArrowLeft size={16} />
              {t(m, 'not_found.back_home', 'Back to home')}
            </Link>
          </div>

          <div className="not-found-route formal-panel p-6 md:p-8" data-reveal data-spotlight>
            <div className="flex items-center justify-between pb-5 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 font-mono text-xs"><Database size={17} className="text-amber-600" />route-monitor</div>
              <SearchX size={18} className="text-rose-500" />
            </div>
            <div className="not-found-route-line mt-10">
              {['SOURCE', 'PROCESS', 'INSIGHT'].map((item, index) => <div key={item} className="not-found-route-node"><i /> <span>0{index + 1} · {item}</span></div>)}
              <div className="not-found-route-break"><strong>×</strong><span>404 · DELIVERY ROUTE</span></div>
            </div>
            <div className="mt-10 rounded-xl border border-slate-200 dark:border-slate-700 p-4 font-mono text-[10px] marketing-subtext leading-6">
              <div>&gt; lifecycle.status: <span className="text-emerald-600">operational</span></div>
              <div>&gt; requested.route: <span className="text-rose-500">unresolved</span></div>
              <div>&gt; recommended.action: return_home</div>
            </div>
          </div>
        </div>
      </section>
    </MarketingLayout>
  );
};

export default NotFound;
