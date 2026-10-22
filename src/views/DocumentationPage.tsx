// @ts-nocheck
'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart3, BookOpen, CheckCircle2, ChevronDown, CircleHelp, Database, FileUp, Gauge, KeyRound, Search, ShieldCheck, Table2, Workflow } from '@/components/icons';
import MarketingLayout from '../components/marketing/MarketingLayout';
import { useLocaleRouting } from '../context/LocaleRoutingContext';
import { localePath } from '../utils/locale.js';

const COPY = {
  en: {
    product: 'PRODUCT DOCUMENTATION', search: 'Search documentation...', overview: 'Platform overview', helpful: 'Was this helpful?', yes: 'Yes', no: 'No', toc: 'ON THIS PAGE',
    groups: [['GETTING STARTED', ['Introduction', 'Create your workspace', 'Your first analysis']], ['DATA CONNECTIONS', ['Connect a file', 'Connect a database', 'Connect an API']], ['DATA PREPARATION', ['Data profiling', 'Column mapping', 'Data quality checks']], ['ANALYSIS & DELIVERY', ['Ask questions', 'Build dashboards', 'Share insights']], ['SECURITY & GOVERNANCE', ['Access control', 'Lineage and audit trail', 'Usage and limits']]],
    title: 'MataQorLab Platform', lead: 'MataQorLab is a governed analytics workspace that helps teams connect data, define trusted business logic, and turn questions into decision-ready answers.',
    intro: 'Start by creating a workspace and connecting the sources your team already uses. Every analysis remains linked to its data, definitions, and validation history.',
    sections: [
      ['Workspace', 'A workspace is the shared operating area for your team. It keeps data connections, datasets, metric definitions, and analysis history together.', ['Invite the people who need to work with the data', 'Set clear workspace ownership', 'Keep sensitive sources scoped to the right team']],
      ['Data connections', 'Bring information into MataQorLab from files, databases, or APIs. Connections are saved securely so your team can refresh trusted data without rebuilding the workflow.', ['Files: CSV and spreadsheet uploads for fast exploration', 'Databases: select only the tables and views you need', 'APIs: use endpoint configuration and pagination controls']],
      ['Data preparation', 'Before data is used for analysis, MataQorLab profiles its structure and highlights missing values, data types, and potential quality issues. Use this stage to establish a reliable dataset.', ['Review column types and sample records', 'Map fields to meaningful business roles', 'Resolve issues before publishing results']],
      ['Analysis', 'Ask questions in natural language or work from the analysis workspace. MataQorLab combines your data with approved definitions, then returns charts, tables, and explanation you can inspect.', ['Ask a focused business question', 'Check the source and calculation context', 'Save findings your team can return to']],
      ['Governed delivery', 'Turn validated findings into reusable dashboards, reports, and decision workflows. Ownership, access, and data refresh status remain visible after you share.', ['Share only with the intended audience', 'Track freshness and quality signals', 'Keep a traceable record of decisions']],
    ],
    calloutTitle: 'A governed path to every answer', callout: 'Use a shared definition for each KPI. This prevents duplicate calculations and gives every stakeholder the same basis for a decision.',
    next: 'NEXT GUIDE',
  },
  th: {
    product: 'คู่มือผลิตภัณฑ์', search: 'ค้นหาในคู่มือ...', overview: 'ภาพรวมแพลตฟอร์ม', helpful: 'บทความนี้มีประโยชน์หรือไม่?', yes: 'มี', no: 'ไม่มี', toc: 'เนื้อหาในหน้านี้',
    groups: [['เริ่มต้นใช้งาน', ['บทนำ', 'สร้าง workspace', 'การวิเคราะห์ครั้งแรก']], ['การเชื่อมต่อข้อมูล', ['เชื่อมต่อไฟล์', 'เชื่อมต่อฐานข้อมูล', 'เชื่อมต่อ API']], ['การเตรียมข้อมูล', ['Data profiling', 'Column mapping', 'ตรวจคุณภาพข้อมูล']], ['การวิเคราะห์และส่งมอบ', ['ถามคำถาม', 'สร้าง dashboard', 'แชร์ Insight']], ['ความปลอดภัยและ governance', ['ควบคุมสิทธิ์', 'Lineage และ audit trail', 'การใช้งานและขีดจำกัด']]],
    title: 'แพลตฟอร์ม MataQorLab', lead: 'MataQorLab คือ workspace สำหรับการวิเคราะห์ข้อมูลแบบกำกับได้ ช่วยให้ทีมเชื่อมข้อมูล กำหนด logic ธุรกิจที่เชื่อถือได้ และเปลี่ยนคำถามเป็นคำตอบที่พร้อมใช้ตัดสินใจ',
    intro: 'เริ่มจากสร้าง workspace และเชื่อมแหล่งข้อมูลที่ทีมใช้อยู่ ทุกการวิเคราะห์เชื่อมโยงกับข้อมูล คำนิยาม และประวัติการตรวจสอบเสมอ',
    sections: [
      ['Workspace', 'Workspace คือพื้นที่ทำงานร่วมกันของทีม เก็บ data connection, dataset, คำนิยาม metric และประวัติการวิเคราะห์ไว้ในที่เดียว', ['เชิญเฉพาะคนที่ต้องทำงานกับข้อมูล', 'กำหนดผู้รับผิดชอบ workspace ให้ชัดเจน', 'จำกัดแหล่งข้อมูลสำคัญให้เฉพาะทีมที่เหมาะสม']],
      ['การเชื่อมต่อข้อมูล', 'นำข้อมูลเข้า MataQorLab ได้จากไฟล์ ฐานข้อมูล หรือ API โดยระบบจัดเก็บ connection อย่างปลอดภัย เพื่อให้ทีม refresh ข้อมูลที่เชื่อถือได้โดยไม่ต้องสร้าง workflow ใหม่', ['ไฟล์: CSV และ spreadsheet สำหรับเริ่มสำรวจอย่างรวดเร็ว', 'ฐานข้อมูล: เลือกเฉพาะ table และ view ที่จำเป็น', 'API: ใช้การตั้งค่า endpoint และ pagination']],
      ['การเตรียมข้อมูล', 'ก่อนใช้วิเคราะห์ MataQorLab จะ profile โครงสร้างข้อมูลและแสดงค่าว่าง ประเภทข้อมูล และประเด็นคุณภาพที่อาจต้องแก้ไข ใช้ขั้นนี้เพื่อสร้าง dataset ที่เชื่อถือได้', ['ตรวจประเภท column และตัวอย่างข้อมูล', 'Map field ให้ตรงกับบทบาททางธุรกิจ', 'แก้ปัญหาก่อนเผยแพร่ผลลัพธ์']],
      ['การวิเคราะห์', 'ถามด้วยภาษาปกติหรือทำงานจาก analysis workspace โดย MataQorLab จะใช้ข้อมูลร่วมกับคำนิยามที่อนุมัติแล้ว และแสดงกราฟ ตาราง และคำอธิบายที่ตรวจสอบได้', ['ถามคำถามธุรกิจที่เจาะจง', 'ตรวจข้อมูลต้นทางและบริบทการคำนวณ', 'บันทึกผลที่ทีมกลับมาใช้อ้างอิงได้']],
      ['การส่งมอบที่กำกับได้', 'เปลี่ยนผลที่ตรวจสอบแล้วเป็น dashboard รายงาน และ workflow ที่นำกลับมาใช้ซ้ำได้ โดยผู้รับผิดชอบ สิทธิ์เข้าถึง และสถานะการ refresh ยังคงมองเห็นได้หลังแชร์', ['แชร์ให้เฉพาะผู้ที่เกี่ยวข้อง', 'ติดตาม freshness และสัญญาณคุณภาพ', 'เก็บประวัติการตัดสินใจที่ตรวจสอบได้']],
    ],
    calloutTitle: 'เส้นทางที่กำกับได้สำหรับทุกคำตอบ', callout: 'ใช้คำนิยามร่วมกันสำหรับแต่ละ KPI เพื่อลดการคำนวณซ้ำซ้อน และทำให้ทุกคนตัดสินใจจากตัวเลขชุดเดียวกัน',
    next: 'คู่มือถัดไป',
  },
};

const groupIcons = [BookOpen, Database, Table2, BarChart3, ShieldCheck];
const sectionIcons = [Workflow, Database, FileUp, Search, Gauge];
const GUIDE_SLUGS = [
  ['introduction', 'create-workspace', 'first-analysis'],
  ['connect-file', 'connect-database', 'connect-api'],
  ['data-profiling', 'column-mapping', 'data-quality-checks'],
  ['ask-with-ai', 'build-dashboards', 'share-insights'],
  ['access-control', 'lineage-audit-trail', 'usage-limits'],
];
const GUIDES = {
  introduction: { en: ['Introduction', 'Understand the governed analytics lifecycle and how the workspace keeps every decision connected to its evidence.'], th: ['บทนำ', 'ทำความเข้าใจ lifecycle การวิเคราะห์แบบกำกับได้ และวิธีที่ workspace เชื่อมทุกการตัดสินใจเข้ากับหลักฐาน'] },
  'create-workspace': { en: ['Create your workspace', 'Set up a shared operating area for people, data connections, definitions, and analysis history.'], th: ['สร้าง workspace', 'ตั้งค่าพื้นที่ทำงานร่วมกันสำหรับทีม การเชื่อมต่อข้อมูล คำนิยาม และประวัติการวิเคราะห์'] },
  'first-analysis': { en: ['Your first analysis', 'Move from a prepared dataset to a focused question, an inspectable answer, and a saved finding.'], th: ['การวิเคราะห์ครั้งแรก', 'เปลี่ยน dataset ที่พร้อมใช้ให้เป็นคำถามที่ชัดเจน คำตอบที่ตรวจสอบได้ และ Insight ที่บันทึกไว้'] },
  'connect-file': { en: ['Connect a file', 'Upload a file, inspect its structure, and prepare it for a governed analysis workflow.'], th: ['เชื่อมต่อไฟล์', 'อัปโหลดไฟล์ ตรวจโครงสร้าง และเตรียมให้พร้อมสำหรับ workflow การวิเคราะห์แบบกำกับได้'] },
  'connect-database': { en: ['Connect a database', 'Create a secure database connection and select only the tables and views needed by the team.'], th: ['เชื่อมต่อฐานข้อมูล', 'สร้างการเชื่อมต่อฐานข้อมูลอย่างปลอดภัย และเลือกเฉพาะ table หรือ view ที่ทีมต้องใช้'] },
  'connect-api': { en: ['Connect an API', 'Configure an API source with clear endpoints, authentication, and pagination behaviour.'], th: ['เชื่อมต่อ API', 'ตั้งค่าแหล่งข้อมูล API ด้วย endpoint, authentication และพฤติกรรม pagination ที่ชัดเจน'] },
  'data-profiling': { en: ['Data profiling', 'Review data structure and quality signals before the dataset is used in analysis or shared with the team.'], th: ['Data profiling', 'ตรวจโครงสร้างและสัญญาณคุณภาพข้อมูล ก่อนนำ dataset ไปวิเคราะห์หรือแชร์ให้ทีม'] },
  'column-mapping': { en: ['Column mapping', 'Give source fields consistent business roles so metrics and analysis use the right context.'], th: ['Column mapping', 'กำหนดบทบาททางธุรกิจให้ field ต้นทางอย่างสม่ำเสมอ เพื่อให้ metric และการวิเคราะห์ใช้บริบทที่ถูกต้อง'] },
  'data-quality-checks': { en: ['Data quality checks', 'Identify missing, inconsistent, or unexpected values before they affect a business conclusion.'], th: ['ตรวจคุณภาพข้อมูล', 'ระบุค่าว่าง ข้อมูลไม่สอดคล้อง หรือค่าที่ผิดคาด ก่อนส่งผลกระทบต่อข้อสรุปทางธุรกิจ'] },
  'ask-with-ai': { en: ['Ask questions', 'Ask focused business questions in natural language while keeping the data and calculation context visible.'], th: ['ถามคำถาม', 'ถามคำถามธุรกิจด้วยภาษาปกติ โดยยังเห็นข้อมูลและบริบทการคำนวณอย่างชัดเจน'] },
  'build-dashboards': { en: ['Build dashboards', 'Turn validated metrics and findings into a shared view of business performance.'], th: ['สร้าง dashboard', 'เปลี่ยน metric และ Insight ที่ตรวจสอบแล้วเป็นมุมมองผลการดำเนินงานที่ทีมใช้ร่วมกัน'] },
  'share-insights': { en: ['Share insights', 'Deliver a verified finding to the right stakeholders with its context and ownership intact.'], th: ['แชร์ Insight', 'ส่งมอบ Insight ที่ตรวจสอบแล้วให้ผู้เกี่ยวข้อง พร้อมบริบทและผู้รับผิดชอบที่ชัดเจน'] },
  'access-control': { en: ['Access control', 'Control who can access workspaces, data sources, and shared analytical outcomes.'], th: ['ควบคุมสิทธิ์', 'ควบคุมผู้ที่เข้าถึง workspace แหล่งข้อมูล และผลลัพธ์การวิเคราะห์ที่แชร์ได้'] },
  'lineage-audit-trail': { en: ['Lineage and audit trail', 'Trace an answer from its source through preparation, logic, and delivery history.'], th: ['Lineage และ audit trail', 'ติดตามคำตอบย้อนกลับไปยังข้อมูลต้นทาง การเตรียมข้อมูล logic และประวัติการส่งมอบ'] },
  'usage-limits': { en: ['Usage and limits', 'Monitor workspace usage and keep analytical work within the capacity of your plan.'], th: ['การใช้งานและขีดจำกัด', 'ติดตามการใช้งาน workspace และดูแลงานวิเคราะห์ให้อยู่ภายในขีดความสามารถของแผนบริการ'] },
};

export default function DocumentationPage() {
  const routing = useLocaleRouting();
  const pathname = usePathname();
  const copy = COPY[routing.locale === 'en' ? 'en' : 'th'];
  const activeSlug = pathname.match(/\/documentation\/([^/]+)$/)?.[1];
  const activeGuide = activeSlug ? GUIDES[activeSlug] : null;
  const isGuidePage = Boolean(activeGuide);
  const guideCopy = activeGuide?.[routing.locale === 'en' ? 'en' : 'th'];
  const articleSections = isGuidePage ? [
    [routing.locale === 'en' ? 'Before you begin' : 'ก่อนเริ่มต้น', guideCopy[1], routing.locale === 'en' ? ['Confirm you have access to the relevant workspace', 'Identify the data owner and intended outcome', 'Use a trusted source before sharing results'] : ['ยืนยันว่าคุณมีสิทธิ์เข้าถึง workspace ที่เกี่ยวข้อง', 'ระบุเจ้าของข้อมูลและผลลัพธ์ที่ต้องการ', 'ใช้แหล่งข้อมูลที่เชื่อถือได้ก่อนแชร์ผลลัพธ์']],
    [routing.locale === 'en' ? 'Recommended workflow' : 'Workflow ที่แนะนำ', routing.locale === 'en' ? `Work through ${guideCopy[0]} in a deliberate sequence. Keep the business context and validation evidence with the work as it progresses.` : `ทำงานในหัวข้อ ${guideCopy[0]} ตามลำดับที่ชัดเจน และเก็บบริบททางธุรกิจรวมถึงหลักฐานการตรวจสอบไว้กับงานตลอดขั้นตอน`, routing.locale === 'en' ? ['Open the relevant workspace or dataset', 'Review configuration and source context', 'Save the verified result for your team'] : ['เปิด workspace หรือ dataset ที่เกี่ยวข้อง', 'ตรวจ configuration และบริบทของข้อมูลต้นทาง', 'บันทึกผลที่ตรวจสอบแล้วให้ทีมใช้อ้างอิง']],
    [routing.locale === 'en' ? 'Verify and continue' : 'ตรวจสอบและทำงานต่อ', routing.locale === 'en' ? 'Before relying on the outcome, confirm that its data freshness, definitions, and access scope are appropriate for the decision.' : 'ก่อนนำผลลัพธ์ไปใช้ตัดสินใจ ให้ยืนยันว่า freshness ของข้อมูล คำนิยาม และขอบเขตสิทธิ์เข้าถึงเหมาะสมแล้ว', routing.locale === 'en' ? ['Review the source and metric definition', 'Check quality signals and refresh status', 'Share only with the intended audience'] : ['ตรวจข้อมูลต้นทางและคำนิยาม metric', 'ตรวจสัญญาณคุณภาพและสถานะ refresh', 'แชร์เฉพาะกับผู้ที่เกี่ยวข้อง']],
  ] : copy.sections;
  const articleTitle = isGuidePage ? guideCopy[0] : copy.title;
  const articleLead = isGuidePage ? guideCopy[1] : copy.lead;
  const guideOrder = GUIDE_SLUGS.flat();
  const nextGuideSlug = isGuidePage ? guideOrder[guideOrder.indexOf(activeSlug) + 1] : 'data-profiling';
  const [query, setQuery] = useState('');
  const [openGroups, setOpenGroups] = useState(copy.groups.map((_, index) => index < 2));
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleGroups = useMemo(() => copy.groups.map(([label, links], index) => [label, links.filter((link) => !normalizedQuery || `${label} ${link}`.toLocaleLowerCase().includes(normalizedQuery)), index]).filter(([, links]) => links.length), [copy.groups, normalizedQuery]);
  const toggleGroup = (index) => setOpenGroups((state) => state.map((value, itemIndex) => itemIndex === index ? !value : value));

  return <MarketingLayout mainClassName="documentation-shell">
    <div className="documentation-topbar">
      <div className="max-w-[1440px] mx-auto px-4 md:px-6 h-full flex items-center gap-3">
        <BookOpen size={16} className="text-amber-600" /><span className="font-mono text-[11px] tracking-[.13em] font-bold marketing-heading">{copy.product}</span>
        <div className="ml-auto relative w-full max-w-xs hidden sm:block"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.search} className="documentation-search w-full pl-9 pr-3 py-2 text-xs" /></div>
      </div>
    </div>

    <div className="documentation-layout max-w-[1440px] mx-auto">
      <aside className="documentation-sidebar">
        <div className="sm:hidden relative mb-5"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.search} className="documentation-search w-full pl-9 pr-3 py-2 text-xs" /></div>
        {visibleGroups.map(([label, links, index]) => { const Icon = groupIcons[index]; const expanded = normalizedQuery || openGroups[index]; return <section key={label} className="documentation-nav-group"><button onClick={() => toggleGroup(index)} className="documentation-nav-title"><span className="flex items-center gap-2"><Icon size={14} />{label}</span><ChevronDown size={14} className={expanded ? '' : '-rotate-90'} /></button>{expanded && <div className="mt-2 space-y-1">{links.map((link, linkIndex) => { const slug = GUIDE_SLUGS[index][linkIndex]; const href = slug === 'introduction' ? localePath('/documentation', routing) : localePath(`/documentation/${slug}`, routing); return <Link href={href} key={link} className={`documentation-nav-link ${activeSlug === slug || (!isGuidePage && slug === 'introduction') ? 'documentation-nav-link-active' : ''}`}>{link}</Link>; })}</div>}</section>; })}
        {!visibleGroups.length && <p className="text-xs marketing-subtext px-3 py-4">{routing.locale === 'en' ? 'No guides found.' : 'ไม่พบคู่มือที่ค้นหา'}</p>}
      </aside>

      <main className="documentation-article" id="overview">
        <div className="documentation-breadcrumb"><span>{copy.product}</span><span>/</span><strong>{isGuidePage ? articleTitle : copy.overview}</strong></div>
        <h1 className="marketing-heading text-4xl md:text-5xl font-bold tracking-tight mt-6">{articleTitle}</h1>
        <p className="documentation-lead">{articleLead}</p>
        <div className="documentation-meta"><span className="system-live-status"><i />VERIFIED GUIDE</span><span>{routing.locale === 'en' ? 'Updated for the current workspace flow' : 'อัปเดตตาม workflow ของ workspace ปัจจุบัน'}</span></div>
        {!isGuidePage && <p className="documentation-body">{copy.intro}</p>}

        {articleSections.map(([title, description, bullets], index) => { const Icon = sectionIcons[index]; return <section key={title} id={`section-${index}`} className="documentation-section scroll-mt-28"><div className="flex items-center gap-3"><div className="documentation-section-icon"><Icon size={18} strokeWidth={1.5} /></div><h2>{title}</h2></div><p className="documentation-body">{description}</p><ul className="documentation-list">{bullets.map((bullet) => <li key={bullet}><CheckCircle2 size={16} />{bullet}</li>)}</ul>{index === 1 && <div className="documentation-callout"><KeyRound size={18} /><div><strong>{copy.calloutTitle}</strong><p>{copy.callout}</p></div></div>}</section>; })}

        {nextGuideSlug && <div className="documentation-next"><span>{copy.next}</span><Link href={localePath(`/documentation/${nextGuideSlug}`, routing)}>{GUIDES[nextGuideSlug][routing.locale === 'en' ? 'en' : 'th'][0]} <span>→</span></Link></div>}
      </main>

      <aside className="documentation-toc"><div className="sticky top-24"><p>{copy.toc}</p>{articleSections.map(([title], index) => <a key={title} href={`#section-${index}`}>{title}</a>)}<div className="documentation-feedback"><CircleHelp size={16} /><strong>{copy.helpful}</strong><div><button aria-label={copy.yes}>✓ {copy.yes}</button><button aria-label={copy.no}>× {copy.no}</button></div></div></div></aside>
    </div>
  </MarketingLayout>;
}
