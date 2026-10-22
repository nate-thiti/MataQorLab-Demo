import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { ResetPassword } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.reset_password");
export default makePublicPage({ View: ResetPassword });
