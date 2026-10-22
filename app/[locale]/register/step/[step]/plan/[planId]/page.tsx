import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { Register } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.register");
export default makePublicPage({ View: Register });
