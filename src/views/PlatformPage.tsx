// @ts-nocheck
'use client';

import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Eye,
  Gauge,
  Layers3,
  MessageSquare,
  Network,
  Workflow,
} from '@/components/icons';
import MarketingLayout from '../components/marketing/MarketingLayout';
import PipelineArchitecture from '../components/marketing/PipelineArchitecture';
import CtaPanel from '../components/marketing/CtaPanel';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';

const COPY = {
  en: {
    kicker: 'PLATFORM ARCHITECTURE',
    title: 'A governed workflow for daily business reporting',
    desc: 'MataQorLab prepares supported data, computes traceable findings, and keeps data readiness separate from human-reviewed business context.',
    principles: [
      ['Traceable by design', 'Computed findings retain formula, source columns, query and result hashes where available.'],
      ['Deterministic compute', 'Supported metrics are calculated by analytical code before the language model narrates them.'],
      ['Review by scope', 'Computation, data readiness, and business context are shown as separate assurance statuses.'],
    ],
    control: 'CONTROL PLANE',
    controlTitle: 'Evidence for each analytical result',
    controlDesc: 'Review the saved data contract, source columns, cleaning recipe, quality signals, formulas, hashes, and ETL run history that are available for the selected workflow.',
    controls: ['Finding provenance', 'Data contract', 'Quality signals', 'Owner-scoped access', 'ETL run history', 'Storage quota'],
    engine: 'ANALYSIS ENGINE',
    engineTitle: 'From approved definitions to reviewable findings',
    engineDesc: 'The analysis layer combines semantic mapping with computed KPI logic, then presents findings through chat, visualization, dashboards, and audit evidence.',
    outputs: ['Computed findings', 'Visualization', 'Dashboard / Chat', 'Analysis audit'],
    ctaTitle: 'Build on a data system you can explain.',
    ctaDesc: 'Connect your first source and establish a governed path to decision.',
    cta: 'Start with MataQorLab',
  },
  th: {
    kicker: 'สถาปัตยกรรมแพลตฟอร์ม',
    title: 'Workflow ที่กำกับได้สำหรับรายงานธุรกิจประจำวัน',
    desc: 'MataQorLab เตรียมข้อมูลที่รองรับ คำนวณผลลัพธ์ที่ตรวจสอบย้อนกลับได้ และแยกความพร้อมข้อมูลออกจากบริบทธุรกิจที่มนุษย์ตรวจแล้ว',
    principles: [
      ['ตรวจสอบที่มาได้ตั้งแต่ต้น', 'ผลลัพธ์ที่คำนวณเก็บสูตร คอลัมน์ต้นทาง query และ hash เมื่อมีข้อมูลรองรับ'],
      ['คำนวณแบบ deterministic', 'Metric ที่รองรับคำนวณด้วย analytical code ก่อนให้โมเดลภาษาเขียนคำอธิบาย'],
      ['ทบทวนตามขอบเขต', 'แสดงสถานะการคำนวณ ความพร้อมข้อมูล และบริบทธุรกิจแยกจากกัน'],
    ],
    control: 'CONTROL PLANE',
    controlTitle: 'หลักฐานประกอบผลวิเคราะห์แต่ละรายการ',
    controlDesc: 'ตรวจข้อตกลงข้อมูล คอลัมน์ต้นทาง Cleaning recipe สัญญาณคุณภาพ สูตร hash และประวัติ ETL ที่มีอยู่สำหรับ workflow ที่เลือก',
    controls: ['ที่มาของ Finding', 'ข้อตกลงข้อมูล', 'สัญญาณคุณภาพ', 'สิทธิ์ตามเจ้าของ', 'ประวัติ ETL', 'Storage quota'],
    engine: 'ANALYSIS ENGINE',
    engineTitle: 'จากนิยามที่อนุมัติแล้ว สู่ผลลัพธ์ที่ทบทวนได้',
    engineDesc: 'ชั้นวิเคราะห์ผสาน Semantic Mapping กับ KPI logic ที่คำนวณ แล้วแสดงผ่าน chat, visualization, dashboard และหลักฐาน audit',
    outputs: ['Computed findings', 'Visualization', 'Dashboard / Chat', 'Analysis audit'],
    ctaTitle: 'สร้างระบบข้อมูลที่คุณอธิบายได้ทุกขั้นตอน',
    ctaDesc: 'เชื่อมต่อแหล่งข้อมูลแรก และสร้างเส้นทางที่กำกับได้ไปสู่การตัดสินใจ',
    cta: 'เริ่มต้นกับ MataQorLab',
  },
};

const PlatformPage = () => {
  const routing = useLocaleRouting();
  const copy = COPY[routing.locale === 'en' ? 'en' : 'th'];
  const principleIcons = [Eye, CheckCircle2, Gauge];

  return (
    <MarketingLayout mainClassName="marketing-page-shell">
      <section className="marketing-page-hero">
        <div className="max-w-6xl mx-auto relative z-10" data-reveal>
          <div className="marketing-page-kicker mb-6">{copy.kicker}</div>
          <h1 className="marketing-heading text-4xl md:text-6xl font-bold tracking-tight leading-[1.08] max-w-4xl">{copy.title}</h1>
          <p className="marketing-subtext text-base md:text-lg leading-relaxed max-w-2xl mt-7">{copy.desc}</p>
        </div>
      </section>

      <section className="px-6 py-20 max-w-6xl mx-auto">
        <div className="grid md:grid-cols-3 gap-5">
          {copy.principles.map(([title, desc], index) => {
            const Icon = principleIcons[index];
            return (
              <article key={title} className="formal-panel p-7" data-reveal data-spotlight style={{ '--reveal-delay': `${index * 90}ms` }}>
                <Icon className="w-6 h-6 text-amber-600 dark:text-amber-400 mb-8" strokeWidth={1.4} />
                <div className="text-[10px] font-mono text-slate-400 mb-3">0{index + 1}</div>
                <h2 className="text-lg font-bold mb-3">{title}</h2>
                <p className="marketing-subtext text-sm leading-relaxed">{desc}</p>
              </article>
            );
          })}
        </div>
      </section>

      <PipelineArchitecture compact />

      <section className="px-6 py-24 max-w-6xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div data-reveal>
            <div className="marketing-page-kicker mb-5">{copy.control}</div>
            <h2 className="marketing-heading text-3xl md:text-5xl font-bold tracking-tight">{copy.controlTitle}</h2>
            <p className="marketing-subtext mt-5 leading-relaxed">{copy.controlDesc}</p>
            <div className="grid grid-cols-2 gap-3 mt-8">
              {copy.controls.map((item) => <div key={item} className="flex items-center gap-2 text-sm"><CheckCircle2 size={15} className="text-emerald-600" />{item}</div>)}
            </div>
          </div>
          <div className="formal-panel p-6 md:p-8" data-reveal data-spotlight>
            <div className="flex justify-between items-center pb-5 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-3"><Network size={19} className="text-amber-600" /><span className="font-mono text-xs">system-control-plane</span></div>
              <span className="system-live-status"><i />ACTIVE</span>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-5">
              {[['3', 'Assurance statuses'], ['VERSIONED', 'ETL recipes'], ['OWNER', 'Access scope'], ['REQUIRED', 'Business review']].map(([value, label]) => (
                <div key={label} className="rounded-xl border border-slate-200 dark:border-slate-700 p-4">
                  <strong className="block font-mono text-xl marketing-heading">{value}</strong><span className="text-[10px] marketing-subtext uppercase tracking-wider">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="marketing-section-alt px-6 py-24">
        <div className="max-w-6xl mx-auto grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-5" data-reveal>
            <div className="marketing-page-kicker mb-5">{copy.engine}</div>
            <h2 className="marketing-heading text-3xl md:text-4xl font-bold tracking-tight">{copy.engineTitle}</h2>
            <p className="marketing-subtext mt-5 leading-relaxed">{copy.engineDesc}</p>
          </div>
          <div className="lg:col-span-7 grid sm:grid-cols-2 gap-4">
            {copy.outputs.map((item, index) => {
              const icons = [MessageSquare, BarChart3, Workflow, Layers3];
              const Icon = icons[index];
              return <div key={item} className="formal-panel p-6 flex items-center justify-between" data-reveal data-spotlight style={{ '--reveal-delay': `${index * 70}ms` }}><div className="flex items-center gap-3"><Icon size={19} className="text-amber-600" /><strong className="text-sm">{item}</strong></div><ArrowRight size={15} className="text-slate-400" /></div>;
            })}
          </div>
        </div>
      </section>

      <CtaPanel title={copy.ctaTitle} description={copy.ctaDesc} buttonText={copy.cta} buttonTo={localePath('/register', routing)} buttonVariant="secondary" />
    </MarketingLayout>
  );
};

export default PlatformPage;
