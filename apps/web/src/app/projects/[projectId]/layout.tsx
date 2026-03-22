"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  FolderPlus,
  LoaderCircle,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  PencilLine,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { createProject, deleteProject, renameProject, type ProjectSummary } from "@/lib/uploadApi";
import { ProjectProvider, useProject } from "./ProjectProvider";

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
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  return (
    <div
      className="group relative flex items-start border transition-colors"
      style={{
        borderColor: active ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.08)",
        background: active ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.02)",
      }}
    >
      <Link
        href={`/projects/${project.project_id}/dashboard`}
        className={`block flex-1 py-3 transition-colors ${collapsed ? "px-0 text-center" : "px-4"}`}
        title={collapsed ? project.name : undefined}
      >
        <div className="flex items-center gap-2">
          {collapsed ? (
            <div className="mx-auto flex h-6 w-6 items-center justify-center rounded-sm bg-white/10 text-xs font-bold text-white/70">
              {project.name.charAt(0).toUpperCase()}
            </div>
          ) : (
            <div className="truncate text-sm font-medium text-white/88">{project.name}</div>
          )}
        </div>
        {!collapsed && (
          <>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] uppercase tracking-[0.16em] text-white/38">
              <span>{formatStatus(project.status)}</span>
              <span>{formatRelativeDate(project.last_activity_at)}</span>
            </div>
            {project.document_filename && (
              <div className="mt-2 truncate text-xs text-white/48">{project.document_filename}</div>
            )}
          </>
        )}
      </Link>

      {!collapsed && (
        <div className="relative pt-3 pr-2" ref={menuRef}>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setMenuOpen(!menuOpen);
            }}
            className="rounded p-1 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
          >
            <MoreVertical className="h-4 w-4" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-32 border border-white/10 bg-[rgba(15,15,25,0.95)] py-1 shadow-xl backdrop-blur-md">
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setMenuOpen(false);
                  onRename(project);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-white/80 transition-colors hover:bg-white/10"
              >
                <PencilLine className="h-3.5 w-3.5" />
                Rename
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setMenuOpen(false);
                  onDelete(project);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 transition-colors hover:bg-red-400/10"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ProjectLayoutInner({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { projectId, loading, projects, detail, workspaceError, setWorkspaceError, refreshSidebar, setDetail } = useProject();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [renameMode, setRenameMode] = useState(false);
  const [renameValue, setRenameValue] = useState(detail?.project?.name || "");
  const [renaming, setRenaming] = useState(false);
  
  const [inlineRenameProject, setInlineRenameProject] = useState<ProjectSummary | null>(null);
  const [inlineRenameValue, setInlineRenameValue] = useState("");

  const currentProject = detail?.project;

  useEffect(() => {
    if (!renameMode && currentProject) {
      setRenameValue(currentProject.name);
    }
  }, [currentProject?.name, renameMode]);

  async function handleNewProject() {
    const name = prompt("Enter a name for the new analysis:", "Untitled analysis");
    if (name === null) return;
    const project = await createProject(name || "Untitled analysis");
    router.push(project.workspace_url || `/projects/${project.project_id}/dashboard`);
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
      alert(error instanceof Error ? error.message : "Failed to rename project.");
    }
  }

  async function handleDeleteProject(p: ProjectSummary) {
    if (!confirm(`Are you sure you want to delete "${p.name}"?`)) return;
    try {
      await deleteProject(p.project_id);
      await refreshSidebar();
      if (p.project_id === projectId) {
        router.push("/");
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to delete project.");
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--background)] px-6 py-10 text-white">
        <div className="mx-auto flex min-h-[70vh] max-w-6xl items-center justify-center gap-3 border border-white/10 bg-white/[0.02]">
          <LoaderCircle className="h-5 w-5 animate-spin text-white/70" />
          <span className="text-white/70">Loading project workspace...</span>
        </div>
      </main>
    );
  }

  const tabs = [
    { name: "Dashboard", href: `/projects/${projectId}/dashboard` },
    { name: "Setup Checklist", href: `/projects/${projectId}/checklist` },
    { name: "Checklist Result", href: `/projects/${projectId}/checklist/result` },
    { name: "Final Review", href: `/projects/${projectId}/review` },
  ];

  return (
    <main className="flex h-screen overflow-hidden bg-[linear-gradient(180deg,#06060e_0%,#080815_52%,#06060d_100%)] text-white">
      {/* Sidebar */}
      <aside
        className={`relative z-20 flex shrink-0 flex-col border-r border-white/10 bg-[rgba(5,5,14,0.96)] transition-all duration-300 ${
          sidebarOpen ? "w-[300px]" : "w-[72px]"
        }`}
      >
        <div className="flex h-16 items-center justify-between border-b border-white/8 px-4">
          <div
            className={`flex items-center gap-3 overflow-hidden transition-opacity duration-300 ${
              sidebarOpen ? "opacity-100" : "w-0 opacity-0"
            }`}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center border border-white/10 bg-white/[0.03] text-white/90">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div className="truncate">
              <div className="text-sm font-medium text-white/90">Merlin AI</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-white/50 transition-colors hover:bg-white/10 hover:text-white"
          >
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </button>
        </div>

        <div className={`flex-1 overflow-y-auto px-3 py-5 ${sidebarOpen ? "" : "px-2"}`}>
          <button
            type="button"
            onClick={() => void handleNewProject()}
            title={sidebarOpen ? undefined : "New Analysis"}
            className="flex w-full items-center justify-center gap-2 border border-white/12 bg-white px-3 py-2.5 text-sm font-medium text-black transition-colors hover:bg-white/90"
          >
            <FolderPlus className="h-4 w-4 shrink-0" />
            {sidebarOpen && <span>New Analysis</span>}
          </button>

          {sidebarOpen && (
            <div className="mt-8 mb-4 flex items-center justify-between px-1">
              <div className="text-[11px] uppercase tracking-[0.22em] text-white/36">Projects</div>
              <Link href="/" className="text-xs text-white/48 hover:text-white/75">
                Home
              </Link>
            </div>
          )}

          {!sidebarOpen && (
            <div className="mt-8 flex justify-center">
               <Link href="/" title="Home" className="text-white/40 hover:text-white/80 p-2">
                 <ArrowLeft className="h-5 w-5" />
               </Link>
            </div>
          )}

          <div className="mt-4 space-y-2">
            {projects.map((project) => {
              if (inlineRenameProject?.project_id === project.project_id && sidebarOpen) {
                return (
                  <div key={project.project_id} className="border border-white/20 bg-black/40 p-3">
                    <input
                      autoFocus
                      value={inlineRenameValue}
                      onChange={(e) => setInlineRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleInlineRenameSubmit();
                        if (e.key === "Escape") setInlineRenameProject(null);
                      }}
                      className="w-full bg-transparent text-sm text-white outline-none"
                    />
                    <div className="mt-2 flex items-center gap-2">
                      <button onClick={() => void handleInlineRenameSubmit()} className="text-[10px] uppercase text-white/70">Save</button>
                      <button onClick={() => setInlineRenameProject(null)} className="text-[10px] uppercase text-white/40">Cancel</button>
                    </div>
                  </div>
                );
              }
              return (
                <SidebarProjectItem
                  key={project.project_id}
                  project={project}
                  active={project.project_id === projectId}
                  collapsed={!sidebarOpen}
                  onRename={(p) => {
                    if (!sidebarOpen) setSidebarOpen(true);
                    setInlineRenameProject(p);
                    setInlineRenameValue(p.name);
                  }}
                  onDelete={(p) => void handleDeleteProject(p)}
                />
              );
            })}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <section className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -top-[16%] left-[8%] h-[32vw] w-[32vw] bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent_60%)]" />
          <div className="absolute right-[8%] top-[18%] h-[28vw] w-[28vw] bg-[radial-gradient(circle,rgba(20,184,166,0.08),transparent_62%)]" />
        </div>

        <div className="relative z-10 mx-auto flex h-full w-full max-w-7xl flex-1 flex-col overflow-hidden px-5 py-6 md:px-8 md:py-8">
          <div className="mb-5 shrink-0">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-sm text-white/50 transition-colors hover:text-white/85"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Link>
          </div>

          <header className="shrink-0 border border-white/10 bg-[rgba(8,8,24,0.92)] px-5 py-5 md:px-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.22em] text-white/35">Analysis Session</div>
                {!renameMode ? (
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <h1 className="truncate text-3xl font-semibold tracking-tight text-white/95 md:text-4xl">
                      {currentProject?.name}
                    </h1>
                    <button
                      type="button"
                      onClick={() => setRenameMode(true)}
                      className="inline-flex items-center gap-2 text-sm text-white/52 transition-colors hover:text-white/82"
                    >
                      <PencilLine className="h-4 w-4" />
                      Rename
                    </button>
                  </div>
                ) : (
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                    <input
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
                      className="w-full border border-white/12 bg-black/25 px-4 py-3 text-white outline-none focus:border-white/25 sm:max-w-xl"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => void handleRename()}
                        disabled={renaming || !renameValue.trim()}
                        className="inline-flex items-center gap-2 border border-white/10 bg-white px-4 py-3 text-sm font-medium text-black disabled:opacity-60"
                      >
                        {renaming ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setRenameMode(false);
                          setRenameValue(currentProject?.name || "");
                        }}
                        className="inline-flex items-center gap-2 border border-white/10 px-4 py-3 text-sm text-white/72"
                      >
                        <X className="h-4 w-4" />
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                <p className="mt-4 max-w-3xl text-sm leading-6 text-white/48 md:text-base">
                  One project owns the uploaded DPA, parsing job, checklist draft, and the later final review.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="border border-white/10 bg-white/[0.02] px-4 py-4">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Project Status</div>
                  <div className="mt-2 text-sm text-white/85">{formatStatus(currentProject?.status || "EMPTY")}</div>
                </div>
                <div className="border border-white/10 bg-white/[0.02] px-4 py-4">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-white/35">Last Activity</div>
                  <div className="mt-2 text-sm text-white/85">
                    {currentProject?.last_activity_at ? formatRelativeDate(currentProject.last_activity_at) : "Just now"}
                  </div>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="mt-6 -mx-5 -mb-5 flex overflow-x-auto border-t border-white/10 px-5 md:-mx-6 md:px-6">
              {tabs.map((tab) => {
                const isActive = pathname.startsWith(tab.href);
                return (
                  <Link
                    key={tab.name}
                    href={tab.href}
                    className={`whitespace-nowrap border-b-2 px-4 py-4 text-sm font-medium transition-colors ${
                      isActive
                        ? "border-indigo-500 text-white"
                        : "border-transparent text-white/50 hover:border-white/30 hover:text-white/80"
                    }`}
                  >
                    {tab.name}
                  </Link>
                );
              })}
            </div>
          </header>

          {workspaceError && (
            <div className="mt-5 shrink-0 border border-red-300/20 bg-red-400/5 px-4 py-3 text-sm text-red-100/85">
              {workspaceError}
            </div>
          )}

          <div className="mt-6 min-h-0 flex-1 overflow-y-auto pr-1">{children}</div>
        </div>
      </section>
    </main>
  );
}

import { use } from "react";

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
