// @ts-nocheck
'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown } from '@/components/icons';

/**
 * Themed select matching LocaleSwitcher / ScheduledEtl SystemSelect.
 * Avoids native OS select chrome that breaks app visuals.
 */
export default function AppSelect({
  value,
  onChange,
  options = [],
  disabled = false,
  placeholder = '—',
  className = '',
  buttonClassName = '',
  'aria-label': ariaLabel,
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const listId = useId();
  const selected = options.find((option) => String(option.value) === String(value));
  const label = selected?.label ?? placeholder;

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => {
          if (!disabled) setOpen((current) => !current);
        }}
        className={`app-input flex w-full items-center justify-between gap-3 px-3 py-3 text-left text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
          open
            ? 'border-[#d97706] ring-2 ring-[#d97706]/15'
            : 'hover:border-amber-300 dark:hover:border-amber-700'
        } ${buttonClassName}`}
      >
        <span className={`min-w-0 flex-1 truncate ${selected ? 'text-slate-800 dark:text-slate-100' : 'text-slate-400'}`}>
          {label}
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-[#d97706] transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      {open && !disabled && (
        <div
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          className="absolute left-0 right-0 top-[calc(100%+0.4rem)] z-[80] max-h-64 overflow-y-auto rounded-xl border border-slate-200/90 bg-white/95 p-1.5 shadow-xl backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95"
        >
          {options.map((option) => {
            const isSelected = String(option.value) === String(value);
            return (
              <button
                key={String(option.value)}
                type="button"
                role="option"
                aria-selected={isSelected}
                disabled={option.disabled}
                onClick={() => {
                  if (option.disabled) return;
                  onChange(option.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors disabled:opacity-40 ${
                  isSelected
                    ? 'bg-amber-50 font-semibold text-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
                    : 'font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {isSelected ? <Check size={14} className="shrink-0 text-amber-700 dark:text-amber-400" /> : null}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
