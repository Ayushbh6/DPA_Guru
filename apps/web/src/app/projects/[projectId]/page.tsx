import { redirect } from "next/navigation";

export default function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  return params.then((p) => {
    redirect(`/projects/${p.projectId}/dashboard`);
  });
}
