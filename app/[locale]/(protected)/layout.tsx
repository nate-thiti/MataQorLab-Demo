import { redirect } from "next/navigation";
import ProtectedShell from "@/app/_components/ProtectedShell";
import { isE2eAuthBypass } from "@/src/utils/supabase/e2eAuth";
import { createSupabaseServerClient } from "@/src/utils/supabase/server";

type ProtectedLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function ProtectedLayout({
  children,
  params,
}: ProtectedLayoutProps) {
  const { locale } = await params;

  if (await isE2eAuthBypass()) {
    return <ProtectedShell>{children}</ProtectedShell>;
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect(`/${locale}/login`);
  }

  return <ProtectedShell>{children}</ProtectedShell>;
}
