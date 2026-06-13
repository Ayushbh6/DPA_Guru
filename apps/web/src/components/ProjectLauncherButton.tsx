"use client";

import { startTransition, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, Plus } from "lucide-react";

import { createVendorReview } from "@/lib/uploadApi";
import { useAuth } from "@/components/AuthProvider";

type Props = {
  className?: string;
  label?: string;
  icon?: boolean;
};

export default function ProjectLauncherButton({
  className = "",
  label = "Begin Review",
  icon = false,
}: Props) {
  const router = useRouter();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    if (!user) {
      router.push("/login");
      return;
    }
    if (loading) return;
    setLoading(true);
    try {
      const vendorName = prompt("Vendor name:");
      if (!vendorName?.trim()) return;
      const intendedUseCase = prompt("Intended use case:");
      if (!intendedUseCase?.trim()) return;
      const project = await createVendorReview({
        vendor_name: vendorName.trim(),
        intended_use_case: intendedUseCase.trim(),
        shares_personal_data: true,
        business_criticality: "medium",
        name: `${vendorName.trim()} Vendor Review`,
      });
      startTransition(() => {
        router.push(project.workspace_url || `/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`);
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <button type="button" onClick={handleClick} disabled={loading} className={className}>
      {loading ? (
        <>
          <LoaderCircle className="h-4 w-4 animate-spin" />
          <span>Creating Review</span>
        </>
      ) : (
        <>
          {icon && <Plus className="h-4 w-4" />}
          <span>{label}</span>
        </>
      )}
    </button>
  );
}
