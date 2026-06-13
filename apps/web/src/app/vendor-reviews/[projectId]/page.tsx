import { redirect } from "next/navigation";
import { use } from "react";

export default function VendorReviewPage({ params }: { params: Promise<{ projectId: string }> }) {
  const resolved = use(params);
  redirect(`/vendor-reviews/${resolved.projectId}/dashboard`);
}
