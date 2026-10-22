import { redirect } from "next/navigation";
import { isE2eAuthBypass } from "@/src/utils/supabase/e2eAuth";
import { createSupabaseServerClient } from "@/src/utils/supabase/server";

type RedirectAuthenticatedUserOptions = {
  allowIncompleteRegistration?: boolean;
};

export async function redirectAuthenticatedUser(
  locale: string,
  options: RedirectAuthenticatedUserOptions = {},
) {
  if (await isE2eAuthBypass()) {
    redirect(`/${locale}/dashboard`);
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    if (options.allowIncompleteRegistration) {
      const { data: profile } = await supabase
        .from("profiles")
        .select("plan_id")
        .eq("id", user.id)
        .maybeSingle();

      if (!profile?.plan_id) {
        return;
      }
    }

    redirect(`/${locale}/dashboard`);
  }
}
