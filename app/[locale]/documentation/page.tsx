import { makeGenerateMetadata, makePublicPage } from "@/app/_lib/createViewPage";
import { DocumentationPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.documentation");
export default makePublicPage({ View: DocumentationPage, disableBlobs: true });
