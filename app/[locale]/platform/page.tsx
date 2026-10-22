import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { PlatformPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.platform");
export default makePublicPage({ View: PlatformPage, disableBlobs: true });
