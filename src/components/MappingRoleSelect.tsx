// @ts-nocheck
import { useState, useMemo, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Search } from '@/components/icons';
import { t } from '../utils/i18n.js';

const PANEL_MAX = 300;
const PANEL_MIN = 140;

export default function MappingRoleSelect({ value, onChange, optionGroups, m, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const buttonRef = useRef(null);
  const [panelStyle, setPanelStyle] = useState({
    top: 0,
    left: 0,
    width: 0,
    maxHeight: PANEL_MAX,
  });

  const baseItems = useMemo(
    () => [
      { value: '__none__', label: t(m, 'chat.mapping.skip_column', 'Skip — not used') },
      { value: '__original__', label: t(m, 'chat.mapping.use_original_name', 'Use original name') },
      { value: '__custom__', label: t(m, 'chat.mapping.type_custom', 'Custom name…') },
    ],
    [m]
  );

  const allItems = useMemo(() => {
    const fromGroups = optionGroups.flatMap((g) => g.items || []);
    return [...baseItems, ...fromGroups];
  }, [baseItems, optionGroups]);

  const selectedLabel = allItems.find((i) => i.value === value)?.label ?? value;

  const q = search.trim().toLowerCase();
  const filteredBase = q
    ? baseItems.filter(
        (i) => i.label.toLowerCase().includes(q) || i.value.toLowerCase().includes(q)
      )
    : baseItems;

  const filteredGroups = optionGroups
    .map((group) => ({
      ...group,
      items: (group.items || []).filter(
        (i) => i.label.toLowerCase().includes(q) || i.value.toLowerCase().includes(q)
      ),
    }))
    .filter((g) => g.items.length > 0);

  const hasResults = filteredBase.length > 0 || filteredGroups.length > 0;

  const close = () => {
    setOpen(false);
    setSearch('');
  };

  const pick = (val) => {
    onChange(val);
    close();
  };

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;

    const updatePosition = () => {
      const rect = buttonRef.current.getBoundingClientRect();
      const gap = 6;
      const pad = 8;
      const spaceBelow = window.innerHeight - rect.bottom - pad;
      const spaceAbove = rect.top - pad;
      const openUp = spaceBelow < PANEL_MIN && spaceAbove > spaceBelow;
      const maxHeight = Math.min(
        PANEL_MAX,
        openUp ? Math.max(PANEL_MIN, spaceAbove - gap) : Math.max(PANEL_MIN, spaceBelow - gap)
      );
      const top = openUp ? rect.top - gap - maxHeight : rect.bottom + gap;
      const left = Math.max(pad, Math.min(rect.left, window.innerWidth - rect.width - pad));

      setPanelStyle({
        top,
        left,
        width: rect.width,
        maxHeight,
      });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open]);

  const panel = open && !disabled && (
    <>
      <div className="fixed inset-0 z-[250]" onClick={close} aria-hidden="true" />
      <div
        className="fixed z-[260] flex flex-col overflow-hidden rounded-xl border border-stone-200 bg-white shadow-[0_18px_48px_rgba(15,23,42,0.16)] dark:border-stone-800 dark:bg-zinc-950"
        style={{
          top: panelStyle.top,
          left: panelStyle.left,
          width: panelStyle.width,
          maxHeight: panelStyle.maxHeight,
        }}
      >
        <div className="shrink-0 border-b border-stone-100 bg-stone-50/70 p-2 dark:border-stone-800 dark:bg-zinc-900/70">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t(m, 'chat.mapping.role_search', 'Search roles…')}
              className="w-full rounded-lg border border-stone-200 bg-white py-1.5 pl-8 pr-3 text-xs text-stone-800 outline-none placeholder:text-stone-400 focus:border-amber-500 dark:border-stone-700 dark:bg-zinc-950 dark:text-stone-100"
            />
          </div>
        </div>

        <div className="overflow-y-auto no-scrollbar flex-1 min-h-0 py-1">
          {!hasResults && (
            <p className="px-3 py-4 text-center text-xs text-stone-500">
              {t(m, 'chat.mapping.role_search_empty', 'No matching roles')}
            </p>
          )}

          {filteredBase.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => pick(item.value)}
              className={`w-full px-3 py-2 text-left text-xs transition-colors ${
                value === item.value
                  ? 'bg-amber-50 font-semibold text-amber-800 dark:bg-amber-950/35 dark:text-amber-300'
                  : 'text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-900 dark:hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}

          {filteredGroups.map((group) => (
            <div key={group.group} className="mt-1">
              <div className="bg-stone-50 px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-stone-400 dark:bg-zinc-900/70 dark:text-stone-500">
                {group.group}
              </div>
              {group.items.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => pick(item.value)}
                  className={`w-full px-4 py-2 text-left text-xs transition-colors ${
                    value === item.value
                      ? 'bg-amber-50 font-semibold text-amber-800 dark:bg-amber-950/35 dark:text-amber-300'
                      : 'text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-zinc-900 dark:hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  );

  return (
    <div className="relative min-w-0">
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 font-sans text-xs text-stone-700 outline-none transition-colors focus:border-amber-500 dark:border-stone-700 dark:bg-zinc-950 dark:text-stone-200 ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
        } ${open ? 'border-amber-500 ring-2 ring-amber-500/15' : 'hover:border-stone-300 dark:hover:border-stone-600'}`}
      >
        <span className="truncate text-left">{selectedLabel}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 text-stone-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {typeof document !== 'undefined' && panel && createPortal(panel, document.body)}
    </div>
  );
}
