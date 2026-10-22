/** Stable backend step IDs → UI labels (TH / EN). */

export const WORKFLOW_STEP_ORDER = [
  'inspect',
  'prepare',
  'clean',
  'map',
  'validate',
  'finalize',
];

const LABELS = {
  inspect: { th: 'ตรวจสอบข้อมูล', en: 'Inspect' },
  prepare: { th: 'เตรียมข้อมูล', en: 'Prepare' },
  clean: { th: 'ทำความสะอาด', en: 'Cleaning' },
  map: { th: 'จัดความหมายคอลัมน์', en: 'Mapping' },
  validate: { th: 'ตรวจสอบความพร้อม', en: 'Validation' },
  finalize: { th: 'พร้อมสำหรับวิเคราะห์', en: 'Ready' },
};

const STATUS_LABELS = {
  pending: { th: 'รอ', en: 'Pending' },
  ready: { th: 'พร้อม', en: 'Ready' },
  running: { th: 'กำลังทำ', en: 'Running' },
  awaiting_user: { th: 'รอคำตอบ', en: 'Needs input' },
  completed: { th: 'เสร็จแล้ว', en: 'Completed' },
  failed: { th: 'ไม่สำเร็จ', en: 'Failed' },
  skipped: { th: 'ข้าม', en: 'Skipped' },
  stale: { th: 'ต้องตรวจสอบใหม่', en: 'Needs refresh' },
  superseded: { th: 'ถูกแทนที่', en: 'Superseded' },
};

export function workflowStepLabel(stepType, isEn = false) {
  const entry = LABELS[stepType];
  if (!entry) return stepType || '';
  return isEn ? entry.en : entry.th;
}

export function workflowStatusLabel(status, isEn = false) {
  const entry = STATUS_LABELS[status];
  if (!entry) return status || '';
  return isEn ? entry.en : entry.th;
}

export function runningStepCopy(stepType, isEn = false) {
  const label = workflowStepLabel(stepType, isEn);
  return isEn ? `${label} in progress…` : `กำลัง${label}…`;
}
