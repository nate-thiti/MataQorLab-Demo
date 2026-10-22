import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { SettingsPage } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.settings");
export default makeProtectedPage({ View: SettingsPage });
