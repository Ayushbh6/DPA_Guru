"use client";

import Link from "next/link";
import { ArrowLeft, FolderPlus, MoreVertical, PanelLeftClose, PanelLeftOpen, PencilLine, ShieldCheck, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import type { ProjectSummary } from "@/lib/uploadApi";

import { formatRelativeDate, formatStatus, statusDotColor } from "./workspace-utils";

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
  onRename: (project: ProjectSummary) => void;
  onDelete: (project: ProjectSummary) => void;
}) {
  return (
    <div
      className={`group relative flex items-start rounded-lg border transition-colors ${
        active
          ? "border-border bg-muted/55"
          : "border-transparent hover:border-border/80 hover:bg-muted/35"
      }`}
    >
      <Link
        href={`/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`}
        className={`block flex-1 py-3 transition-colors ${collapsed ? "px-0 text-center" : "px-4"}`}
        title={collapsed ? project.name : undefined}
      >
        <div className="flex items-center gap-2">
          {collapsed ? (
            <div className="mx-auto flex size-6 items-center justify-center rounded-md bg-muted text-xs font-bold text-muted-foreground">
              {project.name.charAt(0).toUpperCase()}
            </div>
          ) : (
            <>
              <span
                className="inline-block size-2 shrink-0 rounded-full"
                style={{ background: statusDotColor(project.status) }}
              />
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
            {project.document_filename ? (
              <div className="mt-2 truncate text-xs text-muted-foreground">{project.document_filename}</div>
            ) : null}
          </>
        )}
      </Link>

      {!collapsed ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Open actions for ${project.name}`}
            className="mr-2 mt-2.5 inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <MoreVertical data-icon="inline-start" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={() => onRename(project)}>
              <PencilLine data-icon="inline-start" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={() => onDelete(project)}>
              <Trash2 data-icon="inline-start" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}

export function ProjectWorkspaceSidebar({
  open,
  projectId,
  projects,
  inlineRenameProject,
  inlineRenameValue,
  onToggle,
  onNewProject,
  onInlineRenameValueChange,
  onInlineRenameSubmit,
  onInlineRenameCancel,
  onStartInlineRename,
  onDeleteProject,
}: {
  open: boolean;
  projectId: string;
  projects: ProjectSummary[];
  inlineRenameProject: ProjectSummary | null;
  inlineRenameValue: string;
  onToggle: () => void;
  onNewProject: () => void;
  onInlineRenameValueChange: (value: string) => void;
  onInlineRenameSubmit: () => void;
  onInlineRenameCancel: () => void;
  onStartInlineRename: (project: ProjectSummary) => void;
  onDeleteProject: (project: ProjectSummary) => void;
}) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-border/80 bg-card/95 transition-all duration-300 md:relative md:inset-auto md:shrink-0 ${
        open
          ? "w-[min(84vw,320px)] translate-x-0 md:w-[260px]"
          : "w-[min(84vw,320px)] -translate-x-full md:w-[72px] md:translate-x-0"
      }`}
    >
      <div className="flex h-14 items-center justify-between border-b border-border/80 px-4">
        <div className={`flex items-center gap-3 overflow-hidden transition-opacity duration-300 ${open ? "opacity-100" : "w-0 opacity-0"}`}>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border/70 text-primary">
            <ShieldCheck data-icon="inline-start" />
          </div>
          <div className="truncate text-sm font-medium text-foreground">Checker</div>
        </div>
        <Button
          type="button"
          onClick={onToggle}
          aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
          variant="ghost"
          size="icon"
          className="shrink-0 text-muted-foreground hover:text-foreground"
        >
          {open ? <PanelLeftClose data-icon="inline-start" /> : <PanelLeftOpen data-icon="inline-start" />}
        </Button>
      </div>

      <div className={`min-h-0 flex-1 overflow-y-auto px-3 py-5 pb-8 ${open ? "" : "px-2"}`}>
        <Button
          type="button"
          onClick={onNewProject}
          title={open ? undefined : "New Vendor Review"}
          className="h-10 w-full"
        >
          <FolderPlus data-icon="inline-start" />
          {open ? <span>New Review</span> : null}
        </Button>

        {open ? (
          <div className="mb-4 mt-8 flex items-center justify-between px-1">
            <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Reviews</div>
            <Link href="/" className="text-xs text-muted-foreground transition-colors hover:text-foreground">
              Home
            </Link>
          </div>
        ) : (
          <div className="mt-8 flex justify-center">
            <Button render={<Link href="/" title="Home" />} variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground">
              <ArrowLeft data-icon="inline-start" />
            </Button>
          </div>
        )}

        <div className="mt-4 flex flex-col gap-2">
          {projects.map((project, index) => {
            if (inlineRenameProject?.project_id === project.project_id && open) {
              return (
                <div key={`${project.project_id}-rename-${index}`} className="rounded-lg border border-border/80 bg-muted/50 p-3">
                  <Input
                    autoFocus
                    value={inlineRenameValue}
                    onChange={(event) => onInlineRenameValueChange(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") onInlineRenameSubmit();
                      if (event.key === "Escape") onInlineRenameCancel();
                    }}
                    className="h-9 rounded-lg bg-background text-sm"
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <Button type="button" onClick={onInlineRenameSubmit} size="xs">
                      Save
                    </Button>
                    <Button type="button" onClick={onInlineRenameCancel} variant="ghost" size="xs">
                      Cancel
                    </Button>
                  </div>
                </div>
              );
            }

            return (
              <SidebarProjectItem
                key={`${project.project_id}-${index}`}
                project={project}
                active={project.project_id === projectId}
                collapsed={!open}
                onRename={onStartInlineRename}
                onDelete={onDeleteProject}
              />
            );
          })}
        </div>
      </div>
    </aside>
  );
}
