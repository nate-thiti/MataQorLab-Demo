import { redirectAuthenticatedUser } from "@/app/_lib/redirectAuthenticatedUser";

type LoginLayoutProps = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export default async function LoginLayout({
  children,
  params,
}: LoginLayoutProps) {
  const { locale } = await params;
  await redirectAuthenticatedUser(locale);

  return children;
}
