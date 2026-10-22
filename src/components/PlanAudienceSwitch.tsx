// @ts-nocheck
import { Building2, User } from '@/components/icons';

const options = [
  {
    value: 'individual',
    Icon: User,
    en: { label: 'Individual', description: 'For personal analytics' },
    th: { label: 'บุคคล', description: 'สำหรับงานวิเคราะห์ส่วนตัว' },
  },
  {
    value: 'business',
    Icon: Building2,
    en: { label: 'Business', description: 'For teams and organizations' },
    th: { label: 'ธุรกิจ', description: 'สำหรับทีมและองค์กร' },
  },
];

const PlanAudienceSwitch = ({ value, onChange, isEn, compact = false }) => (
  <div
    role="tablist"
    aria-label={isEn ? 'Account type' : 'ประเภทบัญชี'}
    className={`grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1.5 dark:border-slate-700 dark:bg-slate-900/70 ${
      compact ? 'w-full' : 'mx-auto max-w-xl'
    }`}
  >
    {options.map(({ value: optionValue, Icon, en, th }) => {
      const copy = isEn ? en : th;
      const active = value === optionValue;
      return (
        <button
          key={optionValue}
          type="button"
          role="tab"
          aria-selected={active}
          onClick={() => onChange(optionValue)}
          className={`flex items-center justify-center gap-3 rounded-lg px-4 py-3 text-left transition-colors ${
            active
              ? 'bg-white text-slate-950 shadow-sm ring-1 ring-slate-200 dark:bg-slate-800 dark:text-white dark:ring-slate-600'
              : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
          }`}
        >
          <Icon size={18} strokeWidth={1.8} className={active ? 'text-amber-600' : ''} />
          <span>
            <span className="block text-sm font-semibold">{copy.label}</span>
            {!compact && (
              <span className="block text-[11px] font-normal opacity-75">{copy.description}</span>
            )}
          </span>
        </button>
      );
    })}
  </div>
);

export default PlanAudienceSwitch;
