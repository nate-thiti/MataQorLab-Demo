import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ locale: string }> };

export default async function RegisterIndexPage({ params }: Props) {
  const { locale } = await params;
  redirect(`/${locale}/register/step/1`);
}
