"use client";

import type { ReactNode } from "react";
import PageWrapper from "@/src/components/PageWrapper";

type Props = {
  children: ReactNode;
  disableBlobs?: boolean;
};

export default function PublicView({ children, disableBlobs = false }: Props) {
  return <PageWrapper disableBlobs={disableBlobs}>{children}</PageWrapper>;
}
