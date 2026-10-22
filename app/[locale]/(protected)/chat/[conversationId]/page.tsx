import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { Chat } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.chat");
export default makeProtectedPage({ View: Chat });
