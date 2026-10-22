'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, GitBranch } from '../../components/icons';

type ChatBranch = {
  id: string;
  is_root?: boolean;
  branch_index?: number;
  title?: string;
};

type ChatBranchSelectorProps = {
  branches: ChatBranch[];
  activeBranchId: string;
  disabled?: boolean;
  isEn?: boolean;
  onSwitch: (branchId: string) => void | Promise<unknown>;
};

export function branchDisplayLabel(branch: ChatBranch | undefined, isEn = false) {
  if (!branch || branch.is_root) return isEn ? 'Main' : 'หลัก';
  const index = branch.branch_index ? `${branch.branch_index}. ` : '';
  return `${index}${branch.title || (isEn ? 'Edited question' : 'แก้ไขคำถาม')}`;
}

export default function ChatBranchSelector({
  branches,
  activeBranchId,
  disabled = false,
  isEn = false,
  onSwitch,
}: ChatBranchSelectorProps) {
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const activeBranch = branches.find((branch) => branch.id === activeBranchId);
  const label = branchDisplayLabel(activeBranch, isEn);
  const isDisabled = disabled || switching;

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const selectBranch = async (branchId: string) => {
    setOpen(false);
    if (!branchId || branchId === activeBranchId || isDisabled) return;
    setSwitching(true);
    try {
      await onSwitch(branchId);
    } finally {
      setSwitching(false);
      buttonRef.current?.focus();
    }
  };

  return (
    <div ref={rootRef} className="relative hidden sm:block">
      <button
        ref={buttonRef}
        type="button"
        disabled={isDisabled}
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={isEn ? 'Chat version' : 'เวอร์ชันแชท'}
        title={isEn ? 'Switch chat version' : 'สลับเวอร์ชันคำถาม'}
        className="inline-flex h-9 max-w-48 items-center gap-1.5 rounded-xl border border-slate-200/80 bg-white/65 px-3 text-[10px] font-medium text-slate-500 shadow-sm backdrop-blur-sm transition-colors hover:border-amber-300/80 hover:text-amber-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/55 dark:text-slate-300 dark:hover:border-amber-700/70 dark:hover:text-amber-300"
      >
        <GitBranch size={14} className="shrink-0 text-amber-700 dark:text-amber-400" />
        <span className="min-w-0 truncate font-semibold text-slate-700 dark:text-slate-200">
          {switching ? (isEn ? 'Switching…' : 'กำลังสลับ…') : label}
        </span>
        <ChevronDown
          size={13}
          className={`ml-0.5 shrink-0 text-amber-700 transition-transform dark:text-amber-400 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label={isEn ? 'Chat versions' : 'เวอร์ชันคำถาม'}
          className="absolute right-0 top-[calc(100%+0.5rem)] z-50 w-64 overflow-hidden rounded-xl border border-slate-200/90 bg-white/95 p-1.5 shadow-xl backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95"
        >
          <div className="px-2.5 pb-1.5 pt-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            {isEn ? 'Question versions' : 'เวอร์ชันคำถาม'}
          </div>
          <div className="max-h-64 overflow-y-auto">
            {branches.map((branch) => {
              const selected = branch.id === activeBranchId;
              return (
                <button
                  key={branch.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => selectBranch(branch.id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${
                    selected
                      ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {branchDisplayLabel(branch, isEn)}
                  </span>
                  {selected && <Check size={14} className="shrink-0 text-amber-700 dark:text-amber-400" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
