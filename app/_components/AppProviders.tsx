"use client";

import { Suspense, type ReactNode } from "react";
import { ThemeProvider } from "@/src/context/ThemeContext";
import { LocaleRoutingProvider } from "@/src/context/LocaleRoutingContext";
import { FileManagerCacheProvider } from "@/src/context/FileManagerCacheContext";
import { AppSidebarProvider } from "@/src/context/AppSidebarContext";
import CookieConsent from "@/src/views/CookieConsent";

type Props = {
  children: ReactNode;
};

export default function AppProviders({ children }: Props) {
  return (
    <ThemeProvider>
      <LocaleRoutingProvider>
        <FileManagerCacheProvider>
          <AppSidebarProvider>
            <Suspense fallback={null}>{children}</Suspense>
          </AppSidebarProvider>
        </FileManagerCacheProvider>
        <CookieConsent />
      </LocaleRoutingProvider>
    </ThemeProvider>
  );
}
