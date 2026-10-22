import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { PrivacyPolicy } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.privacy_policy");
export default makePublicPage({ View: PrivacyPolicy });
