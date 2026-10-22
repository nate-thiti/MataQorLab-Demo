"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronDown, Globe } from "@/components/icons";
import { useLocaleRouting } from "@/src/context/LocaleRoutingContext";
import { getMessages, t } from "@/src/utils/i18n.js";
import {
  LOCALE_LABELS,
  replacePathLocale,
  SUPPORTED_LOCALES,
} from "@/src/utils/locale.js";

type LocaleSwitcherProps = {
  compact?: boolean;
  /** Segmented buttons for marketing nav; dropdown scales to many locales. */
  variant?: "segmented" | "dropdown";
  className?: string;
};

function localeDisplayName(locale: string, isEn: boolean) {
  const meta = LOCALE_LABELS[locale] || {
    short: locale.toUpperCase(),
    name: locale,
    nameEn: locale,
  };
  return isEn ? meta.nameEn : meta.name;
}

function localeOptionLabel(locale: string, isEn: boolean) {
  const short = (LOCALE_LABELS[locale]?.short || locale).toUpperCase();
  return `${localeDisplayName(locale, isEn)} (${short})`;
}

export default function LocaleSwitcher({
  compact = false,
  variant = "segmented",
  className = "",
}: LocaleSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const searchParams = useSearchParams();
  const routing = useLocaleRouting();
  const messages = getMessages(routing.locale);
  const isEn = routing.locale === "en";
  const localeOptions = compact
    ? SUPPORTED_LOCALES.filter((locale) => locale !== routing.locale)
    : SUPPORTED_LOCALES;

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const selectLocale = (locale: string) => {
    setOpen(false);
    if (locale === routing.locale) return;
    const query = searchParams.toString();
    const nextPath = replacePathLocale(pathname, locale);
    router.push(query ? `${nextPath}?${query}` : nextPath);
  };

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  if (variant === "dropdown") {
    const currentLabel = localeOptionLabel(routing.locale, isEn);
    return (
      <div ref={rootRef} className={`relative inline-block min-w-[10.5rem] ${className}`}>
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={t(messages, "navigation.language", "Language")}
          onClick={() => setOpen((current) => !current)}
          className={`inline-flex w-full items-center gap-2 rounded-lg border bg-white py-3 pl-3 pr-2.5 text-sm font-semibold text-slate-800 outline-none transition-colors dark:bg-slate-900 dark:text-slate-100 ${
            open
              ? "border-[#d97706] ring-2 ring-[#d97706]/15"
              : "border-slate-200 hover:border-amber-300 dark:border-slate-700 dark:hover:border-amber-700"
          }`}
        >
          <Globe size={14} className="shrink-0 text-[#d97706]" aria-hidden />
          <span className="min-w-0 flex-1 truncate text-left">{currentLabel}</span>
          <ChevronDown
            size={14}
            className={`shrink-0 text-[#d97706] transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden
          />
        </button>

        {open && (
          <div
            role="listbox"
            aria-label={t(messages, "navigation.language", "Language")}
            className="absolute right-0 top-[calc(100%+0.4rem)] z-50 w-full min-w-[10.5rem] overflow-hidden rounded-xl border border-slate-200/90 bg-white/95 p-1.5 shadow-xl backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95"
          >
            {SUPPORTED_LOCALES.map((locale) => {
              const selected = locale === routing.locale;
              const short = (LOCALE_LABELS[locale]?.short || locale).toUpperCase();
              return (
                <button
                  key={locale}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => selectLocale(locale)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors ${
                    selected
                      ? "bg-amber-50 font-semibold text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
                      : "font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {localeDisplayName(locale, isEn)}
                    <span className="ml-1.5 text-xs font-semibold text-slate-400 dark:text-slate-500">
                      {short}
                    </span>
                  </span>
                  {selected && (
                    <Check size={14} className="shrink-0 text-amber-700 dark:text-amber-400" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label={t(messages, "navigation.language", "Language")}
      className={`inline-flex items-center rounded-lg border border-slate-200 bg-white/70 p-0.5 text-[11px] font-semibold dark:border-slate-700 dark:bg-slate-900/70 ${className}`}
    >
      {!compact && <Globe size={13} className="mx-1.5 text-slate-400" />}
      {localeOptions.map((locale) => {
        const active = locale === routing.locale;
        const label = (LOCALE_LABELS[locale]?.short || locale).toUpperCase();
        return (
          <button
            key={locale}
            type="button"
            aria-pressed={active}
            aria-label={t(
              messages,
              `navigation.switch_to_${locale}`,
              `Switch to ${label}`,
            )}
            onClick={() => selectLocale(locale)}
            className={`rounded-md px-2 py-1 transition-colors ${
              active
                ? "bg-amber-600 text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
