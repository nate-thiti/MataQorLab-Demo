import { notFound } from "next/navigation";
import AppProviders from "@/app/_components/AppProviders";
import { isSupportedLocale } from "@/src/utils/locale.js";

type LocaleLayoutProps = {
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
};

export default async function LocaleLayout({
  children,
  params,
}: LocaleLayoutProps) {
  const { locale } = await params;

  if (!isSupportedLocale(locale)) {
    notFound();
  }

  return <AppProviders>{children}</AppProviders>;
}
