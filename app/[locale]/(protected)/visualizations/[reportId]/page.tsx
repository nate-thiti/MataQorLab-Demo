import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { Visualization } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.visualizations");
export default makeProtectedPage({ View: Visualization });
