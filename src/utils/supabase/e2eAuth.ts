import { cookies } from "next/headers";

export async function isE2eAuthBypass(): Promise<boolean> {
  if (process.env.E2E_AUTH_BYPASS !== "1") return false;
  const cookieStore = await cookies();
  return cookieStore.get("e2e-authenticated")?.value === "1";
}
