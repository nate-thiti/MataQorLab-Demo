import type { Metadata } from "next";
import type { ComponentType } from "react";
import PublicView from "@/app/_components/PublicView";
import { buildPageMetadata } from "@/app/_lib/metadata";

export const PAGE_DYNAMIC = "force-dynamic" as const;

type LocaleParams = { params: Promise<{ locale: string }> };

export function makeGenerateMetadata(titleKey: string) {
  return async function generateMetadata({
    params,
  }: LocaleParams): Promise<Metadata> {
    const { locale } = await params;
    return buildPageMetadata(locale, titleKey);
  };
}

type PublicPageOptions = {
  View: ComponentType;
  disableBlobs?: boolean;
};

export function makePublicPage({ View, disableBlobs }: PublicPageOptions) {
  return function PublicPage() {
    return (
      <PublicView disableBlobs={disableBlobs}>
        <View />
      </PublicView>
    );
  };
}

type ProtectedPageOptions = {
  View: ComponentType;
};

export function makeProtectedPage({ View }: ProtectedPageOptions) {
  return function ProtectedPage() {
    return <View />;
  };
}

type BarePageOptions = {
  View: ComponentType;
};

export function makeBarePage({ View }: BarePageOptions) {
  return function BarePage() {
    return <View />;
  };
}
