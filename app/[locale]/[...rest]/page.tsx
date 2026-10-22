import { makeGenerateMetadata } from "@/app/_lib/createViewPage";
import NotFound from "@/src/views/NotFound";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.not_found");

export default function UnknownRoutePage() {
  return <NotFound />;
}
