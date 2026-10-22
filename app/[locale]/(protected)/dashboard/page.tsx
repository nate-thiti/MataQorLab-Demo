import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { Dashboard } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.dashboard");
export default makeProtectedPage({ View: Dashboard });
