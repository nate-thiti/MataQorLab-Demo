import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { FileManager } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.files");
export default makeProtectedPage({ View: FileManager });
