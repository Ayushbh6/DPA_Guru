"use client";

import Link from "next/link";
import { startTransition, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, FileText, LoaderCircle, Plus, Search, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CheckerPanel, CheckerSurface, SectionHeader, StatusBadge } from "@/components/checker-ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import VendorReviewCreateDialog from "@/components/VendorReviewCreateDialog";
import { useAuth } from "@/components/AuthProvider";
import { listVendorReviews, type ProjectSummary } from "@/lib/uploadApi";

function formatRelativeDate(value: string) {
  const date = new Date(value);
  const diffHours = Math.round((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (diffHours < 1) return "Just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

export default function ActionSection() {
  const router = useRouter();
  const { user } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (modalOpen) {
      const timer = setTimeout(() => searchRef.current?.focus(), 80);
      return () => clearTimeout(timer);
    }
  }, [modalOpen]);

  async function openModal() {
    if (!user) {
      router.push("/login");
      return;
    }
    setSearch("");
    setModalOpen(true);
    setLoadingProjects(true);
    try {
      const items = await listVendorReviews();
      setProjects(items);
    } finally {
      setLoadingProjects(false);
    }
  }

  function openCreateModal() {
    if (!user) {
      router.push("/login");
      return;
    }
    setCreateModalOpen(true);
  }

  const filtered = projects.filter((p) => {
    const q = search.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      (p.vendor_name ?? "").toLowerCase().includes(q) ||
      (p.document_filename ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <section className="relative z-20 flex min-h-[calc(100svh-4rem)] w-full flex-col items-center justify-center px-5 pb-10 pt-16 text-center md:py-20">
      <CheckerSurface className="w-full max-w-5xl p-6 text-left md:p-10">
        <div className="grid gap-8 md:grid-cols-[1fr_0.72fr] md:items-end">
          <SectionHeader
            label="Begin"
            title="Start a Vendor Review."
            description="Create a Checker workspace, add the main DPA and supporting documents, then confirm criteria before the Approval Pack."
          />
          <div className="flex flex-col gap-3 sm:flex-row md:flex-col">
            <Button type="button" size="lg" onClick={openCreateModal} className="h-11 rounded-lg px-5">
              <Plus data-icon="inline-start" className="h-4 w-4" />
              Create Review
            </Button>
            <Button type="button" size="lg" variant="outline" onClick={() => void openModal()} className="h-11 rounded-lg px-5">
              Open Existing
            </Button>
          </div>
        </div>

        <div className="mt-8 grid gap-3 md:grid-cols-3">
            {[
              ["Evidence-led", "Every finding stays tied to the source material."],
              ["Criteria-first", "Confirm the standard before running the approval pack."],
              ["Human approved", "Proposed edits require explicit user approval."],
            ].map(([title, body]) => (
              <CheckerPanel key={title} className="p-4">
                <ShieldCheck className="mb-3 size-4 text-primary" />
                <div className="text-sm font-medium text-foreground">{title}</div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
              </CheckerPanel>
            ))}
        </div>
      </CheckerSurface>

      <VendorReviewCreateDialog
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        onCreated={(project) => {
          startTransition(() => {
            router.push(project.workspace_url || `/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`);
          });
        }}
      />

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl rounded-xl p-0">
          <DialogHeader className="px-6 pb-2 pt-6">
            <DialogTitle className="text-2xl">Saved reviews</DialogTitle>
            <DialogDescription>Open an existing workspace and continue from the latest review state.</DialogDescription>
          </DialogHeader>
          <div className="px-6 pb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" style={{ color: "var(--text-3)" }} />
              <Input
                ref={searchRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search reviews..."
                className="h-10 rounded-lg pl-9"
              />
            </div>
          </div>
          <ScrollArea className="max-h-[420px] border-t border-border">
            {loadingProjects ? (
              <div className="flex items-center gap-3 px-6 py-10 text-sm text-muted-foreground">
                <LoaderCircle className="h-4 w-4 animate-spin" />
                Loading saved reviews...
              </div>
            ) : filtered.length ? (
              <div className="grid p-3">
                {filtered.map((project, index) => (
                  <Link
                    key={`${project.project_id}-${index}`}
                    href={`/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`}
                    onClick={() => setModalOpen(false)}
                    className="group flex items-center justify-between gap-4 rounded-lg px-4 py-4 transition-colors hover:bg-muted"
                  >
                    <div className="flex min-w-0 items-start gap-3">
                      <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-background">
                        <FileText className="size-4 text-primary" />
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{project.vendor_name || project.name}</div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <StatusBadge>{statusLabel(project.status)}</StatusBadge>
                          {project.document_filename ? <span className="truncate">{project.document_filename}</span> : null}
                          <span>{formatRelativeDate(project.last_activity_at)}</span>
                        </div>
                      </div>
                    </div>
                    <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </Link>
                ))}
              </div>
            ) : (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                {search ? "No matching reviews." : "No saved reviews yet."}
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </section>
  );
}
