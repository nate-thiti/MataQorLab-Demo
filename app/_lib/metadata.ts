import type { Metadata } from "next";
import en from "@/src/locales/en.json";
import th from "@/src/locales/th.json";

type Messages = typeof en;

function getMessages(locale: string): Messages {
  return locale === "en" ? en : th;
}

function translate(messages: Messages, key: string): string {
  const value = key
    .split(".")
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === "object" && part in (acc as object)
          ? (acc as Record<string, unknown>)[part]
          : undefined,
      messages,
    );
  return typeof value === "string" ? value : "";
}

export function buildPageMetadata(
  locale: string,
  titleKey: string,
): Metadata {
  const pageTitle = translate(getMessages(locale), titleKey);
  return {
    title: pageTitle || undefined,
  };
}
