import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { CustomerCenter } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.customer_center");
export default makeProtectedPage({ View: CustomerCenter });
