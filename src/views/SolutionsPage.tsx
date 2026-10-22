// @ts-nocheck
'use client';

import { ArrowUpRight, Building2, Factory, LineChart, Megaphone, ShieldCheck, ShoppingBag } from '@/components/icons';
import MarketingLayout from '../components/marketing/MarketingLayout';
import CtaPanel from '../components/marketing/CtaPanel';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';

const COPY = {
  en: {
    kicker: 'BUSINESS SOLUTIONS',
    title: 'Start with one accountable business workflow.',
    desc: 'Agree on the owner, source, row grain, metric definitions, period status, and decision before expanding the analytical scope.',
    outcomesTitle: 'Candidate pilots, subject to data readiness',
    outcomesDesc: 'Each workflow begins with reconciliation and an approved data contract; availability depends on the supplied fields and quality.',
    sectors: [
      ['Retail & Commerce', 'Unify transactions, inventory, customers, and channels to monitor margin, demand, and retention.', ['Revenue & margin', 'Inventory health', 'Customer behavior']],
      ['Finance & Control', 'Prepare reconciled management views with traceable KPI definitions and audit evidence.', ['Management reporting', 'Variance analysis', 'Audit evidence']],
      ['Operations', 'Review supplied production and service data against quality, capacity, cost, and delivery metrics.', ['Process quality', 'Cost-to-serve', 'Delivery review']],
      ['Marketing & Growth', 'Connect spend, attribution, funnel, and customer value without fragmented spreadsheet logic.', ['Campaign efficiency', 'Funnel conversion', 'Customer value']],
    ],
    valueKicker: 'FROM SIGNAL TO ACTION',
    valueTitle: 'The output changes. The control standard does not.',
    values: [
      ['Agreed metrics', 'Shared KPI definitions make competing versions visible and easier to reconcile.'],
      ['Reviewable decisions', 'Dashboards and chat retain evidence and show which assurance checks remain incomplete.'],
      ['Governed expansion', 'Pilot results, support effort, workload, and quality determine when the next source is added.'],
    ],
    ctaTitle: 'Turn fragmented data work into one operating system.',
    ctaDesc: 'Start with a high-value use case and scale on the same governed lifecycle.',
    cta: 'Design your first solution',
  },
  th: {
    kicker: 'โซลูชันสำหรับธุรกิจ',
    title: 'เริ่มจาก Workflow ธุรกิจหนึ่งเรื่องที่มีผู้รับผิดชอบ',
    desc: 'ตกลงเจ้าของข้อมูล แหล่งข้อมูล grain นิยาม metric สถานะงวด และการตัดสินใจ ก่อนขยายขอบเขตการวิเคราะห์',
    outcomesTitle: 'ตัวอย่าง Pilot ที่ขึ้นกับความพร้อมของข้อมูล',
    outcomesDesc: 'แต่ละ workflow เริ่มจากการกระทบยอดและข้อตกลงข้อมูลที่อนุมัติแล้ว ความสามารถที่ใช้ได้ขึ้นกับ field และคุณภาพข้อมูลที่ได้รับ',
    sectors: [
      ['ค้าปลีกและพาณิชย์', 'รวมธุรกรรม สินค้าคงคลัง ลูกค้า และทุกช่องทาง เพื่อติดตาม margin อุปสงค์ และ retention', ['รายได้และ Margin', 'สุขภาพสินค้าคงคลัง', 'พฤติกรรมลูกค้า']],
      ['การเงินและควบคุม', 'เตรียมมุมมองบริหารที่กระทบยอด พร้อมนิยาม KPI ที่ตรวจสอบได้และหลักฐาน audit', ['รายงานบริหาร', 'วิเคราะห์ความแปรปรวน', 'หลักฐาน Audit']],
      ['ปฏิบัติการ', 'ตรวจข้อมูลการผลิตและบริการที่ได้รับเทียบกับ metric ด้านคุณภาพ capacity ต้นทุน และการส่งมอบ', ['คุณภาพกระบวนการ', 'ต้นทุนการให้บริการ', 'ทบทวนการส่งมอบ']],
      ['การตลาดและการเติบโต', 'เชื่อมงบประมาณ attribution funnel และมูลค่าลูกค้า โดยไม่พึ่ง spreadsheet logic ที่กระจัดกระจาย', ['ประสิทธิภาพแคมเปญ', 'Funnel conversion', 'มูลค่าลูกค้า']],
    ],
    valueKicker: 'จากสัญญาณสู่การลงมือทำ',
    valueTitle: 'รูปแบบผลลัพธ์เปลี่ยนได้ แต่มาตรฐานการควบคุมต้องคงเดิม',
    values: [
      ['Metric ที่ตกลงร่วมกัน', 'นิยาม KPI ร่วมกันทำให้ตัวเลขหลายเวอร์ชันมองเห็นและกระทบยอดได้ง่ายขึ้น'],
      ['การตัดสินใจที่ทบทวนได้', 'Dashboard และ chat เก็บหลักฐานพร้อมแสดง assurance check ที่ยังไม่ครบ'],
      ['ขยายอย่างมีกติกา', 'ผล Pilot ภาระ support workload และคุณภาพ เป็นตัวกำหนดว่าจะเพิ่มแหล่งข้อมูลเมื่อใด'],
    ],
    ctaTitle: 'เปลี่ยนงานข้อมูลที่กระจัดกระจาย ให้เป็นระบบปฏิบัติการเดียว',
    ctaDesc: 'เริ่มจาก use case ที่มีมูลค่าสูง แล้วขยายบน lifecycle ที่กำกับร่วมกัน',
    cta: 'ออกแบบโซลูชันแรก',
  },
};

const SolutionsPage = () => {
  const routing = useLocaleRouting();
  const copy = COPY[routing.locale === 'en' ? 'en' : 'th'];
  const sectorIcons = [ShoppingBag, Building2, Factory, Megaphone];
  const valueIcons = [ShieldCheck, LineChart, Factory];

  return (
    <MarketingLayout mainClassName="marketing-page-shell">
      <section className="marketing-page-hero">
        <div className="max-w-6xl mx-auto relative z-10" data-reveal>
          <div className="marketing-page-kicker mb-6">{copy.kicker}</div>
          <h1 className="marketing-heading text-4xl md:text-6xl font-bold tracking-tight leading-[1.08] max-w-4xl">{copy.title}</h1>
          <p className="marketing-subtext text-base md:text-lg leading-relaxed max-w-2xl mt-7">{copy.desc}</p>
        </div>
      </section>

      <section className="px-6 py-24 max-w-6xl mx-auto">
        <div className="grid md:grid-cols-12 gap-8 items-end mb-12" data-reveal>
          <h2 className="md:col-span-7 marketing-heading text-3xl md:text-4xl font-bold tracking-tight">{copy.outcomesTitle}</h2>
          <p className="md:col-span-5 marketing-subtext text-sm leading-relaxed">{copy.outcomesDesc}</p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          {copy.sectors.map(([title, desc, bullets], index) => {
            const Icon = sectorIcons[index];
            return (
              <article key={title} className="formal-panel p-7 md:p-8 group" data-reveal data-spotlight style={{ '--reveal-delay': `${index % 2 * 90}ms` }}>
                <div className="flex items-start justify-between">
                  <div className="w-11 h-11 rounded-xl bg-amber-600/10 text-amber-700 dark:text-amber-400 grid place-items-center"><Icon size={21} strokeWidth={1.4} /></div>
                  <ArrowUpRight size={18} className="text-slate-400 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
                </div>
                <h3 className="text-xl font-bold mt-8">{title}</h3>
                <p className="marketing-subtext text-sm leading-relaxed mt-3">{desc}</p>
                <div className="flex flex-wrap gap-2 mt-6">{bullets.map((item) => <span key={item} className="px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 text-[10px] font-semibold uppercase tracking-wide marketing-subtext">{item}</span>)}</div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="px-6 py-24 max-w-6xl mx-auto">
        <div className="marketing-page-kicker mb-5" data-reveal>{copy.valueKicker}</div>
        <h2 className="marketing-heading text-3xl md:text-5xl font-bold tracking-tight max-w-3xl" data-reveal>{copy.valueTitle}</h2>
        <div className="grid md:grid-cols-3 gap-5 mt-12">
          {copy.values.map(([title, desc], index) => {
            const Icon = valueIcons[index];
            return <article key={title} className="border-t-2 border-amber-600 pt-6" data-reveal style={{ '--reveal-delay': `${index * 90}ms` }}><Icon size={21} className="text-amber-600 mb-5" strokeWidth={1.4} /><h3 className="font-bold text-lg">{title}</h3><p className="marketing-subtext text-sm leading-relaxed mt-3">{desc}</p></article>;
          })}
        </div>
      </section>

      <CtaPanel title={copy.ctaTitle} description={copy.ctaDesc} buttonText={copy.cta} buttonTo={localePath('/register', routing)} buttonVariant="primary" />
    </MarketingLayout>
  );
};

export default SolutionsPage;
