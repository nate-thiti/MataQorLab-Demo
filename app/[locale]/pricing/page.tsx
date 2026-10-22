import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { PricingPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.pricing");
export default makePublicPage({ View: PricingPage, disableBlobs: true });
