import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { LandingPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.home");
export default makePublicPage({ View: LandingPage, disableBlobs: true });
