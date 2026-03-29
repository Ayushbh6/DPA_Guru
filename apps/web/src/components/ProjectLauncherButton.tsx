"use client";

import { startTransition, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, Plus } from "lucide-react";

import { createProject } from "@/lib/uploadApi";
import { useAuth } from "@/components/AuthProvider";

type Props = {
  className?: string;
  label?: string;
  icon?: boolean;
};

export default function ProjectLauncherButton({
  className = "",
  label = "Begin Analysis",
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
      const project = await createProject();
      startTransition(() => {
        router.push(project.workspace_url || `/projects/${project.project_id}`);
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
          <span>Creating Workspace</span>
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
