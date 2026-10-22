"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import PageWrapper from "@/src/components/PageWrapper";
import { useLocaleRouting } from "@/src/context/LocaleRoutingContext";
import { localePath } from "@/src/utils/locale.js";
import { getE2eMockUser } from "@/src/utils/e2eAuth.js";
import { supabase } from "@/src/utils/supabaseClient.js";

export default function ProtectedShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const routing = useLocaleRouting();

  useEffect(() => {
    if (getE2eMockUser()) return undefined;

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT") {
        router.replace(localePath("/login", routing));
      }
    });

    return () => subscription.unsubscribe();
  }, [router, routing]);

  return <PageWrapper disableBlobs>{children}</PageWrapper>;
}
