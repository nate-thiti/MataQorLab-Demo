import { redirectAuthenticatedUser } from "@/app/_lib/redirectAuthenticatedUser";

type RegisterLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function RegisterLayout({
  children,
  params,
}: RegisterLayoutProps) {
  const { locale } = await params;
  await redirectAuthenticatedUser(locale, {
    allowIncompleteRegistration: true,
  });

  return children;
}
