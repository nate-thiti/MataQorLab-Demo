// @ts-nocheck
'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Activity,
  BarChart3,
  Boxes,
  Calculator,
  CheckCircle2,
  Database,
  FileOutput,
  Filter,
  Gauge,
  Layers3,
  Lightbulb,
  MessageSquareText,
  PackageOpen,
  RefreshCw,
  SearchCheck,
  Send,
} from '@/components/icons';
import { useLocaleRouting } from '../../context/LocaleRoutingContext';

const GROUPS = [
  { id: 'connect', range: '01—03', en: 'Connect', th: 'เชื่อมต่อ' },
  { id: 'govern', range: '04—07', en: 'Prepare & govern', th: 'เตรียมและกำกับ' },
  { id: 'model', range: '08—10', en: 'Model & analyze', th: 'สร้างโมเดลและวิเคราะห์' },
  { id: 'intelligence', range: '11—14', en: 'Intelligence & delivery', th: 'สร้าง Insight และส่งมอบ' },
  { id: 'operate', range: '15—16', en: 'Operate & control', th: 'ปฏิบัติการและควบคุม' },
];

const STAGES = [
  { en: 'Data Source', th: 'แหล่งข้อมูล', group: 'connect', Icon: Database },
  { en: 'Ingestion', th: 'รับข้อมูล', group: 'connect', Icon: PackageOpen },
  { en: 'Raw Storage', th: 'จัดเก็บข้อมูลดิบ', group: 'connect', Icon: Layers3 },
  { en: 'ETL', th: 'กระบวนการ ETL', group: 'govern', Icon: RefreshCw },
  { en: 'Data Cleaning', th: 'ทำความสะอาดข้อมูล', group: 'govern', Icon: Filter },
  { en: 'Validation', th: 'ตรวจสอบความถูกต้อง', group: 'govern', Icon: CheckCircle2 },
  { en: 'Data Quality', th: 'ควบคุมคุณภาพข้อมูล', group: 'govern', Icon: SearchCheck },
  { en: 'Data Modeling', th: 'สร้างโมเดลข้อมูล', group: 'model', Icon: Boxes },
  { en: 'KPI Calculation', th: 'คำนวณ KPI', group: 'model', Icon: Calculator },
  { en: 'Business Analysis', th: 'วิเคราะห์ธุรกิจ', group: 'model', Icon: Gauge },
  { en: 'Insight', th: 'Insight', group: 'intelligence', Icon: Lightbulb },
  { en: 'Visualization', th: 'แสดงผลด้วยภาพ', group: 'intelligence', Icon: BarChart3 },
  { en: 'Dashboard / Chat', th: 'Dashboard / Chat', group: 'intelligence', Icon: MessageSquareText },
  { en: 'Report Generation', th: 'สร้างรายงาน', group: 'intelligence', Icon: FileOutput },
  { en: 'Scheduled Delivery', th: 'ส่งมอบตามกำหนด', group: 'operate', Icon: Send },
  { en: 'Monitoring / Audit / Cost Control', th: 'ติดตาม / ตรวจสอบ / ควบคุมต้นทุน', group: 'operate', Icon: Activity },
];

const COPY = {
  en: {
    eyebrow: 'END-TO-END DATA OPERATING SYSTEM',
    title: 'One governed path from source to decision',
    desc: 'Every dataset moves through a visible, auditable lifecycle—so teams can trust the number, understand its origin, and control the cost of every decision.',
    status: 'Lifecycle active',
  },
  th: {
    eyebrow: 'ระบบปฏิบัติการข้อมูลแบบครบวงจร',
    title: 'เส้นทางเดียวที่กำกับได้ ตั้งแต่ข้อมูลจนถึงการตัดสินใจ',
    desc: 'ข้อมูลทุกชุดเคลื่อนผ่าน lifecycle ที่มองเห็นและตรวจสอบย้อนหลังได้ เพื่อให้ทีมเชื่อมั่นในตัวเลข เข้าใจที่มา และควบคุมต้นทุนของทุกการตัดสินใจ',
    status: 'ระบบกำลังทำงาน',
  },
};

const PipelineArchitecture = ({ className = '', compact = false, title, description }) => {
  const routing = useLocaleRouting();
  const locale = routing.locale === 'en' ? 'en' : 'th';
  const copy = COPY[locale];
  const sectionRef = useRef(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      if (!sectionRef.current) return;
      const rect = sectionRef.current.getBoundingClientRect();
      const travel = rect.height + window.innerHeight * 0.35;
      const passed = window.innerHeight * 0.78 - rect.top;
      setProgress(Math.max(0, Math.min(1, passed / travel)));
    };
    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);

  return (
    <section ref={sectionRef} className={`system-lifecycle ${compact ? 'system-lifecycle-compact' : ''} ${className}`}>
      <div className="max-w-6xl mx-auto px-6">
        <div className="system-lifecycle-header" data-reveal>
          <div>
            <div className="marketing-badge mb-4"><span className="w-8 h-px bg-amber-600/40" />{copy.eyebrow}</div>
            <h2 className="marketing-heading text-3xl md:text-5xl font-bold tracking-tight max-w-3xl">
              {title || copy.title}
            </h2>
          </div>
          <div className="max-w-md md:text-right">
            <p className="marketing-subtext text-sm md:text-base leading-relaxed">{description || copy.desc}</p>
            <div className="system-live-status mt-5 md:ml-auto"><i />{copy.status}</div>
          </div>
        </div>

        <div className="system-lifecycle-groups" data-reveal>
          {GROUPS.map((group) => (
            <div key={group.id} className={`system-group system-group-${group.id}`}>
              <span>{group.range}</span>
              <strong>{group[locale]}</strong>
            </div>
          ))}
        </div>

        <div className="system-flow" style={{ '--flow-progress': progress }}>
          <div className="system-flow-rail"><span /></div>
          {STAGES.map(({ en, th, Icon, group }, index) => (
            <article
              key={en}
              className={`system-stage system-stage-${group}`}
              data-reveal
              data-spotlight
              style={{ '--reveal-delay': `${Math.min(index % 4, 3) * 70}ms` }}
            >
              <div className="system-stage-number">{String(index + 1).padStart(2, '0')}</div>
              <div className="system-stage-icon"><Icon size={18} strokeWidth={1.5} /></div>
              <h3>{locale === 'en' ? en : th}</h3>
              <div className="system-stage-arrow">→</div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
};

export default PipelineArchitecture;
