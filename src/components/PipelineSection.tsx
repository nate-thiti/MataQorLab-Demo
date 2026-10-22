// @ts-nocheck
import { t } from '../utils/i18n.js';
import { BarChart3, Database, FileText, Link2 } from '@/components/icons';

const PipelineSection = ({ m }) => {
  return (
    <section id="solutions" className="py-20 w-full marketing-section-alt px-6">
      <div className="max-w-6xl mx-auto space-y-16">
        
        {/* Header */}
        <div className="text-center max-w-3xl mx-auto space-y-4" data-reveal>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            {t(m, 'landing.pro_tools.title')}
          </h2>
          <p className="marketing-subtext text-sm md:text-base leading-relaxed">
            {t(m, 'landing.pro_tools.desc')}
          </p>
        </div>

        {/* Row of 2 Cards */}
        <div className="grid md:grid-cols-2 gap-8">
          
          {/* Card 1: Dashboard & Interactive Graphs */}
          <div className="marketing-card marketing-card-hover p-8 space-y-6 flex flex-col justify-between overflow-hidden relative" data-reveal data-spotlight>
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-amber-600/10 flex items-center justify-center text-amber-700 dark:text-amber-400">
                <BarChart3 className="w-5 h-5" strokeWidth={1.5} />
              </div>
              <h3 className="text-lg font-bold">{t(m, 'landing.pro_tools.dash_title')}</h3>
              <p className="text-sm marketing-subtext leading-relaxed">
                {t(m, 'landing.pro_tools.dash_desc')}
              </p>
            </div>
            
            {/* Mockup Dashboard Image container */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 h-48 flex flex-col justify-between text-xs text-slate-400">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                <span className="font-semibold text-slate-300 font-mono">Store Revenue Analytics</span>
                <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 text-[9px] font-mono uppercase">Live</span>
              </div>
              <div className="flex gap-4 items-end flex-1 pt-4">
                <div className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full bg-amber-600/30 rounded-t h-16"></div>
                  <span className="text-[8px] font-mono">Mon</span>
                </div>
                <div className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full bg-amber-600/50 rounded-t h-24"></div>
                  <span className="text-[8px] font-mono">Tue</span>
                </div>
                <div className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full bg-amber-600 rounded-t h-32"></div>
                  <span className="text-[8px] font-mono">Wed</span>
                </div>
                <div className="flex-grow flex flex-col items-center justify-center p-2 bg-slate-900/60 rounded-lg border border-slate-800 max-w-[120px] self-center">
                  <span className="text-[8px] uppercase tracking-wider text-slate-500">Gross Margin</span>
                  <span className="text-sm font-bold text-emerald-500 font-mono">38.4%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: API & SQL Connectivity */}
          <div className="marketing-card marketing-card-hover p-8 space-y-6 flex flex-col justify-between" data-reveal data-spotlight style={{ '--reveal-delay': '90ms' }}>
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-amber-600/10 flex items-center justify-center text-amber-700 dark:text-amber-400">
                <Database className="w-5 h-5" strokeWidth={1.5} />
              </div>
              <h3 className="text-lg font-bold">{t(m, 'landing.pro_tools.conn_title')}</h3>
              <p className="text-sm marketing-subtext leading-relaxed">
                {t(m, 'landing.pro_tools.conn_desc')}
              </p>
            </div>
            
            {/* Connection Items */}
            <div className="space-y-3">
              {/* Database connector active */}
              <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800/60">
                <div className="flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-md bg-blue-500/10 text-blue-600 flex items-center justify-center font-bold text-[10px]">
                    Pg
                  </div>
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-350">PostgreSQL Connector</span>
                </div>
                <div className="w-5 h-5 rounded-full bg-emerald-500/10 text-emerald-600 flex items-center justify-center text-xs font-bold">
                  ✓
                </div>
              </div>

              {/* API integration placeholder */}
              <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800/60">
                <div className="flex items-center gap-2.5">
                  <div className="w-6 h-6 rounded-md bg-purple-500/10 text-purple-600 flex items-center justify-center font-bold text-[10px]">
                    API
                  </div>
                  <span className="text-xs font-semibold text-slate-700 dark:text-slate-355">External API Integration</span>
                </div>
                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-mono">Available</span>
              </div>
            </div>
          </div>

        </div>

        {/* Large full-width Panel: File Analysis */}
        <div className="marketing-card p-8" data-reveal data-spotlight>
          <div className="grid md:grid-cols-12 gap-8 items-center">
            {/* Left side info */}
            <div className="md:col-span-6 space-y-4 text-left">
              <h3 className="text-lg font-bold">{t(m, 'landing.pro_tools.file_title')}</h3>
              <p className="text-sm marketing-subtext leading-relaxed">
                {t(m, 'landing.pro_tools.file_desc')}
              </p>
            </div>

            {/* Right side file placeholders */}
            <div className="md:col-span-6 flex flex-wrap gap-4 justify-start md:justify-end">
              {/* File 1: CSV */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 text-emerald-800 dark:text-emerald-400 text-xs font-medium">
                <FileText className="w-5 h-5 shrink-0 text-emerald-600 dark:text-emerald-400" strokeWidth={1.5} />
                <span className="font-mono">Sales_2023.csv</span>
              </div>

              {/* File 2: Parquet */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-amber-500/20 bg-amber-500/5 text-amber-800 dark:text-amber-400 text-xs font-medium">
                <FileText className="w-5 h-5 shrink-0 text-amber-600 dark:text-amber-400" strokeWidth={1.5} />
                <span className="font-mono">Report_Q4.parquet</span>
              </div>

              {/* API Connection */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-purple-500/20 bg-purple-500/5 text-purple-800 dark:text-purple-400 text-xs font-medium">
                <Link2 className="w-5 h-5 shrink-0 text-purple-600 dark:text-purple-400" strokeWidth={1.5} />
                <span className="font-mono">Sales_API (JSON)</span>
              </div>

              {/* SQL Connection */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-indigo-500/20 bg-indigo-500/5 text-indigo-800 dark:text-indigo-400 text-xs font-medium">
                <Database className="w-5 h-5 shrink-0 text-indigo-600 dark:text-indigo-400" strokeWidth={1.5} />
                <span className="font-mono">Production_DB (SQL)</span>
              </div>

              {/* File 3: XLSX */}
              <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-blue-500/20 bg-blue-500/5 text-blue-800 dark:text-blue-400 text-xs font-medium">
                <FileText className="w-5 h-5 shrink-0 text-blue-600 dark:text-blue-400" strokeWidth={1.5} />
                <span className="font-mono">Data_Raw.xlsx</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
};

export default PipelineSection;
