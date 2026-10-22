import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { TermsOfService } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.terms_of_service");
export default makePublicPage({ View: TermsOfService });
