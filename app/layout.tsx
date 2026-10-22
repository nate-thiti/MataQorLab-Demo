import type { Metadata } from "next";
import { headers } from "next/headers";
import Script from "next/script";
import { themeInitScript } from "@/src/utils/themeScript.js";
import { DEFAULT_LOCALE, isSupportedLocale } from "@/src/utils/locale.js";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MataQor",
    template: "MataQor | %s",
  },
  description: "MataQor — Smart AI Analytics",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const requestHeaders = await headers();
  const requestedLocale = requestHeaders.get("x-mataqor-locale");
  const locale = requestedLocale && isSupportedLocale(requestedLocale)
    ? requestedLocale
    : DEFAULT_LOCALE;

  return (
    <html lang={locale} className="h-full antialiased" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* The root App Router layout applies this stylesheet to every route. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link href="https://fonts.googleapis.com/css2?family=Kanit:wght@100;200;300;400;500;600;700;800;900&family=Noto+Sans+Thai:wght@100;200;300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-full flex flex-col">
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: themeInitScript }}
        />
        {children}
      </body>
    </html>
  );
}
