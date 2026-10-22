// @ts-nocheck

function layerLabel(key, isEn) {
  const map = {
    computation: isEn ? 'Computation readiness' : 'Computation readiness',
    dataReadiness: isEn ? 'Data readiness' : 'Data readiness',
    businessContext: isEn ? 'Business context' : 'Business context',
  };
  return map[key] || key;
}

function layerValue(value, isEn) {
  const v = String(value || '').toLowerCase();
  if (v === 'verified') return isEn ? 'Verified' : 'Verified';
  if (v === 'ready') return isEn ? 'Ready' : 'Ready';
  if (v === 'confirmed') return isEn ? 'Confirmed' : 'Confirmed';
  if (v === 'pending') return isEn ? 'Pending' : 'Pending';
  return value || '—';
}

/**
 * Clear ready-for-analysis transition with separate assurance layers.
 */
export default function ReadyForAnalysisCard({
  ready = false,
  assurance = null,
  isEn = false,
}) {
  if (!ready) return null;

  return (
    <section
      className="not-prose mt-3 rounded-2xl border border-emerald-200 bg-emerald-50/65 px-4 py-3.5 dark:border-emerald-900/70 dark:bg-emerald-950/20"
      aria-label={isEn ? 'Ready for analysis' : 'พร้อมสำหรับวิเคราะห์'}
    >
      <p className="text-sm font-semibold text-emerald-900 dark:text-emerald-100">
        ✓ {isEn
          ? 'Dataset is ready for analysis'
          : 'ข้อมูลพร้อมสำหรับวิเคราะห์แล้ว'}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-emerald-800/90 dark:text-emerald-200/80">
        {isEn
          ? 'Data readiness and business context are confirmed. You can ask questions about this dataset.'
          : 'ตรวจสอบข้อมูลและบริบทธุรกิจเรียบร้อย ตอนนี้คุณสามารถถามคำถามเกี่ยวกับข้อมูลชุดนี้ได้'}
      </p>
      {assurance && (
        <dl className="mt-3 grid gap-1.5 border-t border-emerald-200/70 pt-3 text-xs text-stone-700 dark:border-emerald-900/60 dark:text-stone-200">
          {[
            ['computation', assurance.computation],
            ['dataReadiness', assurance.dataReadiness],
            ['businessContext', assurance.businessContext],
          ].map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3">
              <dt>{layerLabel(key, isEn)}</dt>
              <dd className="font-medium">{layerValue(value, isEn)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
