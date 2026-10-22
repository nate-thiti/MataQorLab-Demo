import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { SolutionsPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.solutions");
export default makePublicPage({ View: SolutionsPage, disableBlobs: true });
