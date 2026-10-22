import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { Login } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.login");
export default makePublicPage({ View: Login });
