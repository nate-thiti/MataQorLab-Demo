import { makeGenerateMetadata, makeProtectedPage } from "@/app/_lib/createViewPage";
import { PaymentHistory } from "@/app/_components/dynamicViews";

export const dynamic = "force-dynamic";
export const generateMetadata = makeGenerateMetadata("page_titles.payment_history");
export default makeProtectedPage({ View: PaymentHistory });
