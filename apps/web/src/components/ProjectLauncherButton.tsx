"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import VendorReviewCreateDialog from "@/components/VendorReviewCreateDialog";

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
  const [open, setOpen] = useState(false);

  async function handleClick() {
    if (!user) {
      router.push("/login");
      return;
    }
    setOpen(true);
  }

  return (
    <>
      <button type="button" onClick={handleClick} className={className}>
        <>
          {icon && <Plus className="h-4 w-4" />}
          <span>{label}</span>
        </>
      </button>
      <VendorReviewCreateDialog
        open={open}
        onOpenChange={setOpen}
        onCreated={(project) => {
          setOpen(false);
          router.push(project.workspace_url || `/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`);
        }}
      />
    </>
  );
}
