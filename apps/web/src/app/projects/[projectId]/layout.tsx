"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import {
  ArrowLeft,
  FolderPlus,
  LoaderCircle,
  Moon,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Save,
  ShieldCheck,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button as UiButton } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckerSurface } from "@/components/checker-ui";
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

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return true;
    const stored = localStorage.getItem("theme");
    return stored ? stored === "dark" : true;
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }, [dark]);
  function toggle() {
    const next = !dark;
    setDark(next);
    const theme = next ? "dark" : "light";
    localStorage.setItem("theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }
  return (
    <UiButton
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      variant="ghost"
      size="icon"
      className="shrink-0 text-muted-foreground hover:text-foreground"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </UiButton>
  );
}

function projectStatusStyle(status: string): React.CSSProperties {
  if (status === 'REVIEW_COMPLETE') return { color: 'var(--status-compliant)', background: 'var(--status-compliant-bg)', borderColor: 'var(--status-compliant)' };
  if (status === 'CHECKLIST_APPROVED') return { color: 'var(--status-partial)', background: 'var(--status-partial-bg)', borderColor: 'var(--status-partial)' };
  if (status.includes('FAIL')) return { color: 'var(--status-noncompliant)', background: 'var(--status-noncompliant-bg)', borderColor: 'var(--status-noncompliant)' };
  return { color: 'var(--text-2)', background: 'var(--bg-2)', borderColor: 'var(--line)' };
}

function statusDotColor(status: string): string {
  if (status === 'REVIEW_COMPLETE') return 'var(--status-compliant)';
  if (status === 'CHECKLIST_APPROVED') return 'var(--status-partial)';
  if (status.includes('FAIL')) return 'var(--status-noncompliant)';
  return 'var(--text-3)';
}

function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

function formatRelativeDate(value: string) {
  const date = new Date(value);
  const diffHours = Math.round((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (diffHours < 1) return "Just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function SidebarProjectItem({
  project,
  active,
  collapsed,
  onRename,
  onDelete,
}: {
  project: ProjectSummary;
  active: boolean;
  collapsed: boolean;
  onRename: (p: ProjectSummary) => void;
  onDelete: (p: ProjectSummary) => void;
}) {
  return (
    <div
      className={`group relative flex items-start rounded-lg border transition-colors ${
        active
          ? "border-border bg-muted/60"
          : "border-transparent hover:border-border hover:bg-muted/35"
      }`}
    >
      <Link
        href={`/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`}
        className={`block flex-1 py-3 transition-colors ${collapsed ? "px-0 text-center" : "px-4"}`}
        title={collapsed ? project.name : undefined}
      >
        <div className="flex items-center gap-2">
          {collapsed ? (
            <div
              className="mx-auto flex h-6 w-6 items-center justify-center rounded-md bg-muted text-xs font-bold text-muted-foreground"
            >
              {project.name.charAt(0).toUpperCase()}
            </div>
          ) : (
            <>
              <span className="inline-block h-2 w-2 shrink-0" style={{ background: statusDotColor(project.status), borderRadius: '50%' }} />
              <div className="truncate text-sm font-medium text-foreground">{project.name}</div>
            </>
          )}
        </div>
        {!collapsed && (
          <>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              <span>{formatStatus(project.status)}</span>
              <span>{formatRelativeDate(project.last_activity_at)}</span>
            </div>
            {project.document_filename && (
              <div className="mt-2 truncate text-xs text-muted-foreground">{project.document_filename}</div>
            )}
          </>
        )}
      </Link>

      {!collapsed && (
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Open actions for ${project.name}`}
            className="mr-2 mt-2.5 inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <MoreVertical className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={() => onRename(project)}>
              <PencilLine className="h-3.5 w-3.5" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={() => onDelete(project)}>
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

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
    if (!renameMode) {
      setRenameValue(currentProjectName);
    }
  }, [currentProjectName, renameMode]);

  // Auto-collapse sidebar on mobile
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
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setSidebarOpen(false);
      setMobileOverlay(false);
    }
  }, [pathname]);

  function toggleSidebar() {
    const nextOpen = !sidebarOpen;
    setSidebarOpen(nextOpen);
    if (window.innerWidth < 768) {
      setMobileOverlay(nextOpen);
    }
  }

  function handleNewProject() {
    setCreateDialogOpen(true);
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

  async function handleInlineRenameSubmit() {
    if (!inlineRenameProject || !inlineRenameValue.trim()) return;
    try {
      const updated = await renameProject(inlineRenameProject.project_id, inlineRenameValue);
      if (inlineRenameProject.project_id === projectId) {
        setDetail(updated);
      }
      setInlineRenameProject(null);
      await refreshSidebar();
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to rename project.");
    }
  }

  async function confirmDeleteProject() {
    const p = deleteConfirmProject;
    if (!p) return;
    try {
      await deleteProject(p.project_id);
      setDeleteConfirmProject(null);
      await refreshSidebar();
      if (p.project_id === projectId) {
        router.push("/");
      }
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Failed to delete project.");
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen px-6 py-10 text-foreground">
        <CheckerSurface className="mx-auto flex min-h-[70vh] max-w-6xl items-center justify-center gap-3">
          <LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Loading Checker workspace...</span>
        </CheckerSurface>
      </main>
    );
  }

  if (!detail?.project) {
    return (
      <main className="min-h-screen px-6 py-10 text-foreground">
        <CheckerSurface className="mx-auto flex min-h-[70vh] max-w-3xl flex-col items-center justify-center px-8 text-center">
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
            <UiButton render={<Link href="/" />} className="h-10 px-4">
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </UiButton>
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
    <main className="min-h-svh text-foreground md:flex md:h-svh md:flex-row md:overflow-hidden">
      {/* Mobile overlay backdrop */}
      {mobileOverlay && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => { setSidebarOpen(false); setMobileOverlay(false); }}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-border bg-card/95 transition-all duration-300 md:relative md:inset-auto md:shrink-0 ${
          sidebarOpen
            ? "translate-x-0 w-[min(84vw,320px)] md:w-[260px]"
            : "-translate-x-full w-[min(84vw,320px)] md:w-[72px] md:translate-x-0"
        }`}
      >
        <div className="flex h-12 items-center justify-between border-b border-border px-4 md:h-14">
          <div
            className={`flex items-center gap-3 overflow-hidden transition-opacity duration-300 ${
              sidebarOpen ? "opacity-100" : "w-0 opacity-0"
            }`}
          >
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-primary"
            >
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div className="truncate">
              <div className="text-sm font-medium text-foreground">Checker</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {sidebarOpen && <ThemeToggle />}
            <UiButton
              type="button"
              onClick={toggleSidebar}
              aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
              variant="ghost"
              size="icon"
              className="shrink-0 text-muted-foreground hover:text-foreground"
            >
              {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
            </UiButton>
          </div>
        </div>

        <div className={`flex-1 overflow-y-auto px-3 py-5 pb-8 ${sidebarOpen ? "" : "px-2"}`}>
          <UiButton
            type="button"
            onClick={handleNewProject}
            title={sidebarOpen ? undefined : "New Vendor Review"}
            className="h-10 w-full"
          >
            <FolderPlus className="h-4 w-4 shrink-0" />
            {sidebarOpen && <span>New Review</span>}
          </UiButton>

          {sidebarOpen && (
            <div className="mt-8 mb-4 flex items-center justify-between px-1">
              <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Reviews</div>
              <Link href="/" className="text-xs text-muted-foreground transition-colors hover:text-foreground">
                Home
              </Link>
            </div>
          )}

          {!sidebarOpen && (
            <div className="mt-8 flex justify-center">
              <UiButton render={<Link href="/" title="Home" />} variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-5 w-5" />
              </UiButton>
            </div>
          )}

          <div className="mt-4 space-y-2">
            {projects.map((project, index) => {
              if (inlineRenameProject?.project_id === project.project_id && sidebarOpen) {
                return (
                  <div key={`${project.project_id}-rename-${index}`} className="rounded-lg border border-border bg-muted/60 p-3">
                    <Input
                      autoFocus
                      value={inlineRenameValue}
                      onChange={(e) => setInlineRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleInlineRenameSubmit();
                        if (e.key === "Escape") setInlineRenameProject(null);
                      }}
                      className="h-9 rounded-lg bg-background text-sm"
                    />
                    <div className="mt-2 flex items-center gap-2">
                      <UiButton type="button" onClick={() => void handleInlineRenameSubmit()} size="xs">
                        Save
                      </UiButton>
                      <UiButton type="button" onClick={() => setInlineRenameProject(null)} variant="ghost" size="xs">
                        Cancel
                      </UiButton>
                    </div>
                  </div>
                );
              }
              return (
                <SidebarProjectItem
                  key={`${project.project_id}-${index}`}
                  project={project}
                  active={project.project_id === projectId}
                  collapsed={!sidebarOpen}
                  onRename={(p) => {
                    if (!sidebarOpen) setSidebarOpen(true);
                    setInlineRenameProject(p);
                    setInlineRenameValue(p.name);
                  }}
                  onDelete={setDeleteConfirmProject}
                />
              );
            })}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <section className="relative min-w-0 md:flex md:flex-1 md:flex-col">
        {/* Mobile sidebar toggle button */}
        <UiButton
          type="button"
          onClick={toggleSidebar}
          aria-label="Open sidebar"
          variant="outline"
          size="icon-lg"
          className={`fixed left-4 top-4 z-20 bg-card md:hidden ${
            sidebarOpen ? "pointer-events-none opacity-0" : ""
          }`}
        >
          <PanelLeftOpen className="h-4 w-4" />
        </UiButton>

        <div className="mx-auto w-full max-w-7xl px-4 pb-6 pt-14 md:flex md:min-h-0 md:flex-1 md:flex-col md:overflow-y-auto md:px-5 md:py-4 lg:px-6 lg:py-5">
          <header className="shrink-0 rounded-xl border border-border bg-card px-4 py-3 text-card-foreground shadow-sm md:px-5 lg:px-6">
            <div className="min-w-0">
                {!renameMode ? (
                  <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
                    <div className="min-w-0 flex-1 basis-full sm:basis-auto">
                      <h1 className="truncate text-lg font-semibold tracking-tight text-foreground md:text-xl lg:text-2xl">
                        {currentProject?.name}
                      </h1>
                    </div>
                    <UiButton
                      type="button"
                      onClick={() => setRenameMode(true)}
                      aria-label="Rename review"
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <PencilLine className="h-3.5 w-3.5" />
                    </UiButton>
                    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={projectStatusStyle(currentProject?.status || 'EMPTY')}>
                      <span className="inline-block h-1.5 w-1.5" style={{ background: statusDotColor(currentProject?.status || 'EMPTY'), borderRadius: '50%' }} />
                      {formatStatus(currentProject?.status || "EMPTY")}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {currentProject?.last_activity_at ? formatRelativeDate(currentProject.last_activity_at) : "Just now"}
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <Input
                      autoFocus
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleRename();
                        if (e.key === "Escape") {
                           setRenameMode(false);
                           setRenameValue(currentProject?.name || "");
                        }
                      }}
                      className="h-10 w-full rounded-lg bg-background text-sm sm:max-w-xl"
                    />
                    <div className="flex gap-2">
                      <UiButton
                        type="button"
                        onClick={() => void handleRename()}
                        disabled={renaming || !renameValue.trim()}
                        className="h-10 px-3"
                      >
                        {renaming ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        Save
                      </UiButton>
                      <UiButton
                        type="button"
                        onClick={() => {
                          setRenameMode(false);
                          setRenameValue(currentProject?.name || "");
                        }}
                        variant="outline"
                        className="h-10 px-3"
                      >
                        <X className="h-4 w-4" />
                        Cancel
                      </UiButton>
                    </div>
                  </div>
                )}
            </div>

            <div className="mt-4 border-t border-border pt-3 md:hidden">
              <Select
                items={tabs.map((tab) => ({ value: tab.href, label: tab.name }))}
                value={activeTab.href}
                onValueChange={(href) => {
                  if (typeof href === "string") router.push(href);
                }}
              >
                <SelectTrigger className="h-10 w-full rounded-lg bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="start">
                  <SelectGroup>
                    {tabs.map((tab, tabIdx) => (
                      <SelectItem key={tab.href} value={tab.href}>
                        <span className="mr-2 inline-flex size-5 items-center justify-center rounded-md bg-muted text-[10px] font-semibold text-muted-foreground">
                          {tabIdx + 1}
                        </span>
                        {tab.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            {/* Tabs */}
            <div className="mt-3 -mx-4 -mb-2.5 hidden overflow-x-auto border-t border-border px-4 pr-4 md:-mx-5 md:-mb-2.5 md:flex md:px-5 md:pr-5 lg:-mx-6 lg:-mb-3 lg:px-6 lg:pr-6">
              {tabs.map((tab, tabIdx) => {
                const isActive = tab.href === activeTab.href;
                return (
                  <Link
                    key={tab.name}
                    href={tab.href}
                    aria-label={tab.name}
                    className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-2.5 py-2 text-xs font-medium transition-colors md:px-3 md:py-2 md:text-sm lg:px-3.5 lg:py-2.5 ${
                      isActive
                        ? "border-primary text-foreground"
                        : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                    }`}
                  >
                    <span className={`inline-flex h-5 w-5 items-center justify-center rounded-md text-[10px] font-semibold ${
                      isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                    }`}>{tabIdx + 1}</span>
                    <span>{tab.name}</span>
                  </Link>
                );
              })}
            </div>
          </header>

          {workspaceError && (
            <Alert variant="destructive" className="mt-4 shrink-0 border-destructive/30 bg-[var(--danger-bg)] md:mt-5">
              <AlertDescription className="text-[var(--danger)]">{workspaceError}</AlertDescription>
            </Alert>
          )}

          <div className="mt-2 md:mt-3 md:min-h-0 md:flex-1 md:overflow-y-auto md:pr-1 lg:mt-4">{children}</div>
        </div>
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
            <UiButton type="button" variant="outline" onClick={() => setDeleteConfirmProject(null)}>
              Cancel
            </UiButton>
            <UiButton type="button" variant="destructive" onClick={() => void confirmDeleteProject()}>
              Delete Review
            </UiButton>
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
