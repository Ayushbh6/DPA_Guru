"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { ArrowLeft, LoaderCircle } from "lucide-react";

import { CheckerSurface } from "@/components/checker-ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import VendorReviewCreateDialog from "@/components/VendorReviewCreateDialog";
import { deleteProject, renameProject, type ProjectSummary } from "@/lib/uploadApi";

import { ProjectProvider, useProject } from "./ProjectProvider";
import { ProjectWorkspaceFooter } from "./workspace-footer";
import { ProjectWorkspaceHeader } from "./workspace-header";
import { ProjectWorkspaceSidebar } from "./workspace-sidebar";

function ProjectLayoutInner({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { projectId, loading, projects, detail, workspaceError, setWorkspaceError, refreshSidebar, setDetail } = useProject();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOverlay, setMobileOverlay] = useState(false);
  const [renameMode, setRenameMode] = useState(false);
  const [renameValue, setRenameValue] = useState(detail?.project?.name || "");
  const [renaming, setRenaming] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [inlineRenameProject, setInlineRenameProject] = useState<ProjectSummary | null>(null);
  const [inlineRenameValue, setInlineRenameValue] = useState("");
  const [deleteConfirmProject, setDeleteConfirmProject] = useState<ProjectSummary | null>(null);

  const currentProject = detail?.project;
  const currentProjectName = detail?.project?.name || "";

  useEffect(() => {
    if (!renameMode) setRenameValue(currentProjectName);
  }, [currentProjectName, renameMode]);

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth < 768) {
        setSidebarOpen(false);
        setMobileOverlay(false);
      } else {
        setMobileOverlay(false);
      }
    }

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setSidebarOpen(false);
      setMobileOverlay(false);
    }
  }, [pathname]);

  function openSidebar() {
    setSidebarOpen(true);
    if (window.innerWidth < 768) setMobileOverlay(true);
  }

  function toggleSidebar() {
    const nextOpen = !sidebarOpen;
    setSidebarOpen(nextOpen);
    if (window.innerWidth < 768) setMobileOverlay(nextOpen);
  }

  async function handleRename() {
    if (!projectId || !renameValue.trim()) return;
    setRenaming(true);
    try {
      const updated = await renameProject(projectId, renameValue);
      setDetail(updated);
      setRenameMode(false);
      await refreshSidebar();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to rename project.");
    } finally {
      setRenaming(false);
    }
  }

  function cancelRename() {
    setRenameMode(false);
    setRenameValue(currentProject?.name || "");
  }

  async function handleInlineRenameSubmit() {
    if (!inlineRenameProject || !inlineRenameValue.trim()) return;
    try {
      const updated = await renameProject(inlineRenameProject.project_id, inlineRenameValue);
      if (inlineRenameProject.project_id === projectId) setDetail(updated);
      setInlineRenameProject(null);
      await refreshSidebar();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to rename project.");
    }
  }

  async function confirmDeleteProject() {
    const project = deleteConfirmProject;
    if (!project) return;
    try {
      await deleteProject(project.project_id);
      setDeleteConfirmProject(null);
      await refreshSidebar();
      if (project.project_id === projectId) router.push("/");
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to delete project.");
    }
  }

  if (loading) {
    return (
      <main className="grid h-dvh place-items-center px-6 py-10 text-foreground">
        <CheckerSurface className="flex min-h-[70vh] w-full max-w-6xl items-center justify-center gap-3">
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Loading Checker workspace...</span>
        </CheckerSurface>
      </main>
    );
  }

  if (!detail?.project) {
    return (
      <main className="grid h-dvh place-items-center px-6 py-10 text-foreground">
        <CheckerSurface className="flex min-h-[70vh] w-full max-w-3xl flex-col items-center justify-center px-8 text-center">
          <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            Review Access
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground">
            Vendor Review not available
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-6 text-muted-foreground">
            {workspaceError || "This Vendor Review could not be loaded. It may not exist anymore or you may not have access to it."}
          </p>
          <div className="mt-6">
            <Button render={<Link href="/" />} className="h-10 px-4">
              <ArrowLeft data-icon="inline-start" />
              Back to Home
            </Button>
          </div>
        </CheckerSurface>
      </main>
    );
  }

  const tabs = [
    { name: "Workspace", shortName: "Workspace", href: `/vendor-reviews/${projectId}/dashboard` },
    { name: "Criteria", shortName: "Criteria", href: `/vendor-reviews/${projectId}/checklist` },
    { name: "Approved Criteria", shortName: "Approved", href: `/vendor-reviews/${projectId}/checklist/result` },
    { name: "Approval Pack", shortName: "Pack", href: `/vendor-reviews/${projectId}/review` },
  ];
  const activeTab =
    [...tabs]
      .sort((a, b) => b.href.length - a.href.length)
      .find((tab) => pathname.startsWith(tab.href)) || tabs[0];

  return (
    <main className="h-dvh overflow-hidden text-foreground md:flex md:flex-row">
      {mobileOverlay ? (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[1px] md:hidden"
          onClick={() => {
            setSidebarOpen(false);
            setMobileOverlay(false);
          }}
        />
      ) : null}

      <ProjectWorkspaceSidebar
        open={sidebarOpen}
        projectId={projectId}
        projects={projects}
        inlineRenameProject={inlineRenameProject}
        inlineRenameValue={inlineRenameValue}
        onToggle={toggleSidebar}
        onNewProject={() => setCreateDialogOpen(true)}
        onInlineRenameValueChange={setInlineRenameValue}
        onInlineRenameSubmit={() => void handleInlineRenameSubmit()}
        onInlineRenameCancel={() => setInlineRenameProject(null)}
        onStartInlineRename={(project) => {
          if (!sidebarOpen) setSidebarOpen(true);
          setInlineRenameProject(project);
          setInlineRenameValue(project.name);
        }}
        onDeleteProject={setDeleteConfirmProject}
      />

      <section className="flex h-dvh min-w-0 flex-1 flex-col overflow-hidden">
        <ProjectWorkspaceHeader
          projectName={currentProject?.name || "Vendor Review"}
          status={currentProject?.status || "EMPTY"}
          lastActivityAt={currentProject?.last_activity_at}
          tabs={tabs}
          activeTab={activeTab}
          renameMode={renameMode}
          renameValue={renameValue}
          renaming={renaming}
          onRenameValueChange={setRenameValue}
          onStartRename={() => setRenameMode(true)}
          onCancelRename={cancelRename}
          onSaveRename={() => void handleRename()}
          onOpenSidebar={openSidebar}
        />

        {workspaceError ? (
          <div className="shrink-0 px-4 pt-3 md:px-5 lg:px-6">
            <Alert variant="destructive" className="border-destructive/30 bg-[var(--danger-bg)]">
              <AlertDescription className="text-[var(--danger)]">{workspaceError}</AlertDescription>
            </Alert>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-5 lg:px-6">
          {children}
        </div>

        <ProjectWorkspaceFooter
          tabs={tabs}
          activeTab={activeTab}
          pathname={pathname}
          projectId={projectId}
        />
      </section>

      <VendorReviewCreateDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={(project) => {
          setCreateDialogOpen(false);
          void refreshSidebar();
          router.push(project.workspace_url || `/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`);
        }}
      />
      <Dialog open={!!deleteConfirmProject} onOpenChange={(open) => !open && setDeleteConfirmProject(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete review?</DialogTitle>
            <DialogDescription>
              This removes &quot;{deleteConfirmProject?.name}&quot; from the workspace list. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteConfirmProject(null)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={() => void confirmDeleteProject()}>
              Delete Review
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

export default function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  return (
    <ProjectProvider projectId={projectId}>
      <ProjectLayoutInner>{children}</ProjectLayoutInner>
    </ProjectProvider>
  );
}
