"use client";

import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { createLocaleRouting } from "../utils/locale.js";
import type { LocaleRouting } from "../types/ui";

const LocaleRoutingContext = createContext<LocaleRouting | null>(null);

export function LocaleRoutingProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const value = useMemo(
    () => createLocaleRouting("/", pathname),
    [pathname],
  );

  useEffect(() => {
    document.documentElement.lang = value.locale;
  }, [value.locale]);

  return (
    <LocaleRoutingContext.Provider value={value}>
      {children}
    </LocaleRoutingContext.Provider>
  );
}

export function useLocaleRouting(): LocaleRouting {
  const value = useContext(LocaleRoutingContext);
  if (!value) {
    throw new Error("useLocaleRouting must be used within LocaleRoutingProvider");
  }
  return value;
}
