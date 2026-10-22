// @ts-nocheck
'use client';

import { useEffect, useRef } from 'react';
import { BarChart3, Braces, Database, FileSpreadsheet, ShieldCheck } from '@/components/icons';
import { useLocaleRouting } from '../../context/LocaleRoutingContext';

const COPY = {
  en: {
    eyebrow: 'FROM COMPLEXITY TO CLARITY',
    title: 'Watch raw signals become a decision.',
    desc: 'Scroll through the MataQorLab operating model.',
    source: ['01 · CONNECT', 'Bring every signal into one governed workspace.', 'Files, databases, and APIs arrive with source context intact.'],
    engine: ['02 · GOVERN & COMPUTE', 'Turn fragmented inputs into trusted business logic.', 'Cleaning, validation, modeling, and KPI calculation happen through a controlled processing core.'],
    output: ['03 · DECIDE', 'Deliver an answer people can act on.', 'Verified insights move into visualization, dashboard, chat, and reporting—ready for the next decision.'],
  },
  th: {
    eyebrow: 'จากความซับซ้อนสู่ความชัดเจน',
    title: 'ดูข้อมูลดิบ เปลี่ยนเป็นการตัดสินใจ',
    desc: 'เลื่อนเพื่อสำรวจวิธีทำงานของ MataQorLab',
    source: ['01 · CONNECT', 'รวมทุกสัญญาณเข้าสู่ workspace ที่กำกับได้', 'ไฟล์ ฐานข้อมูล และ API เข้ามาพร้อมบริบทของแหล่งที่มาครบถ้วน'],
    engine: ['02 · GOVERN & COMPUTE', 'เปลี่ยนข้อมูลที่กระจัดกระจายให้เป็น business logic ที่เชื่อถือได้', 'Cleaning, validation, modeling และ KPI calculation ทำงานผ่าน processing core ที่ควบคุมทุกขั้นตอน'],
    output: ['03 · DECIDE', 'ส่งมอบคำตอบที่พร้อมนำไปใช้', 'Insight ที่ตรวจสอบแล้วถูกส่งต่อเป็น visualization, dashboard, chat และ report เพื่อการตัดสินใจถัดไป'],
  },
};

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const smoothstep = (start, end, value) => {
  const x = clamp((value - start) / (end - start));
  return x * x * (3 - 2 * x);
};

const LandingScrollExperience = () => {
  const routing = useLocaleRouting();
  const copy = COPY[routing.locale === 'en' ? 'en' : 'th'];
  const sectionRef = useRef(null);
  const frameRef = useRef(null);

  useEffect(() => {
    const update = () => {
      frameRef.current = null;
      const section = sectionRef.current;
      if (!section) return;
      const rect = section.getBoundingClientRect();
      const scrollable = Math.max(1, rect.height - window.innerHeight);
      const progress = clamp(-rect.top / scrollable);
      const sourceOpacity = 1 - smoothstep(0.12, 0.32, progress);
      const engineOpacity = smoothstep(0.2, 0.37, progress) * (1 - smoothstep(0.61, 0.78, progress));
      const outputOpacity = smoothstep(0.66, 0.84, progress);
      section.style.setProperty('--story-progress', progress.toFixed(4));
      section.style.setProperty('--source-opacity', sourceOpacity.toFixed(4));
      section.style.setProperty('--engine-opacity', engineOpacity.toFixed(4));
      section.style.setProperty('--output-opacity', outputOpacity.toFixed(4));
      section.style.setProperty('--story-title-opacity', (1 - progress * 0.42).toFixed(4));
      section.style.setProperty('--story-title-y', `${progress * -22}px`);
      section.style.setProperty('--story-step-one-y', `${progress * -30}px`);
      section.style.setProperty('--story-step-two-y', `${(0.42 - progress) * 55}px`);
      section.style.setProperty('--story-step-three-y', `${(0.78 - progress) * 55}px`);
      section.style.setProperty('--story-orbit-rotate', `${progress * 90}deg`);
      section.style.setProperty('--source-x', `${progress * -170}px`);
      section.style.setProperty('--source-y', `${progress * -70}px`);
      section.style.setProperty('--source-z', `${progress * -220}px`);
      section.style.setProperty('--source-rotate', `${progress * -28}deg`);
      section.style.setProperty('--engine-y', `${(0.48 - progress) * 65}px`);
      section.style.setProperty('--engine-rotate', `${(progress - 0.5) * 35}deg`);
      section.style.setProperty('--output-x', `${(0.82 - progress) * 130}px`);
      section.style.setProperty('--output-y', `${(0.82 - progress) * 50}px`);
      section.style.setProperty('--output-rotate', `${(0.82 - progress) * 18}deg`);
      section.style.setProperty('--ring-one-rotate', `${progress * 150}deg`);
      section.style.setProperty('--ring-two-rotate', `${progress * -120}deg`);
      section.style.setProperty('--story-hint-opacity', (1 - progress).toFixed(4));
    };
    const requestUpdate = () => {
      if (!frameRef.current) frameRef.current = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', requestUpdate);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      window.removeEventListener('scroll', requestUpdate);
      window.removeEventListener('resize', requestUpdate);
    };
  }, []);

  return (
    <section ref={sectionRef} className="landing-scroll-story">
      <div className="landing-story-sticky">
        <div className="landing-story-grid" aria-hidden="true" />
        <div className="max-w-6xl mx-auto px-6 h-full relative z-10 grid lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-5 landing-story-copy">
            <div className="marketing-page-kicker mb-5">{copy.eyebrow}</div>
            <h2 className="marketing-heading text-3xl md:text-5xl font-bold tracking-tight leading-tight">{copy.title}</h2>
            <p className="marketing-subtext mt-4 text-sm">{copy.desc}</p>

            {[copy.source, copy.engine, copy.output].map(([step, title, desc], index) => (
              <div key={step} className={`landing-story-step landing-story-step-${index + 1}`}>
                <span>{step}</span>
                <h3>{title}</h3>
                <p>{desc}</p>
              </div>
            ))}
          </div>

          <div className="lg:col-span-7 landing-story-scene" aria-hidden="true">
            <div className="landing-scene-orbit" />

            <div className="landing-source-scene">
              <div className="landing-source-card source-card-file"><FileSpreadsheet /><span>SALES_Q4.CSV</span><small>2.4M ROWS</small></div>
              <div className="landing-source-card source-card-db"><Database /><span>PRODUCTION_DB</span><small>LIVE SQL</small></div>
              <div className="landing-source-card source-card-api"><Braces /><span>CRM_API</span><small>JSON · LIVE</small></div>
              <div className="landing-source-beam" />
            </div>

            <div className="landing-engine-scene">
              <div className="landing-engine-ring ring-one" />
              <div className="landing-engine-ring ring-two" />
              <div className="landing-engine-core"><ShieldCheck /><strong>MATAQOR</strong><span>GOVERNED CORE</span></div>
              <div className="landing-engine-check check-one"><ShieldCheck /> VALIDATED</div>
              <div className="landing-engine-check check-two">KPI LOGIC · LOCKED</div>
            </div>

            <div className="landing-output-scene">
              <div className="landing-output-dashboard">
                <div className="landing-output-head"><span>EXECUTIVE OVERVIEW</span><i>LIVE</i></div>
                <div className="landing-output-metric"><small>NET REVENUE</small><strong>฿48.2M</strong><span>+28.4%</span></div>
                <div className="landing-output-chart">{[42, 56, 48, 70, 61, 84, 92].map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</div>
              </div>
              <div className="landing-output-insight"><BarChart3 /><div><small>INSIGHT</small><strong>Growth is led by repeat customers.</strong></div></div>
            </div>
          </div>
        </div>
        <div className="landing-story-scroll-hint"><span /> SCROLL TO TRANSFORM</div>
      </div>
    </section>
  );
};

export default LandingScrollExperience;
