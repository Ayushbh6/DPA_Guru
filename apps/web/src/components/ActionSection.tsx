"use client";

import Link from "next/link";
import { startTransition, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, LoaderCircle, Plus, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { listVendorReviews, type ProjectSummary } from "@/lib/uploadApi";
import { useAuth } from "@/components/AuthProvider";
import VendorReviewCreateDialog from "@/components/VendorReviewCreateDialog";

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
      const timer = setTimeout(() => searchRef.current?.focus(), 50);
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
    <section className="relative z-20 w-full flex flex-col items-center text-center px-6 pt-8 pb-20">
      {/* Vertical divider */}
      <div className="w-px h-6 mb-6" style={{ background: 'var(--line)' }} />

      <div className="relative max-w-2xl w-full">
        <p
          className="mb-5 text-[10px] uppercase tracking-[0.35em] font-medium"
          style={{ color: 'var(--accent)' }}
        >
          Begin
        </p>
        <h2
          className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight"
          style={{ color: 'var(--text)' }}
        >
          Start a Vendor Review.
        </h2>
        <p
          className="mt-4 text-base leading-relaxed max-w-md mx-auto"
          style={{ color: 'var(--text-2)' }}
        >
          Create a Checker workspace, upload the main DPA and supporting documents, then generate review criteria and an Approval Pack.
        </p>

        <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <button
            type="button"
            onClick={openCreateModal}
            className="inline-flex items-center justify-center gap-2 px-8 py-3.5 text-sm font-medium transition-opacity hover:opacity-80"
            style={{ background: 'var(--invert)', color: 'var(--invert-fg)' }}
          >
            <Plus className="h-4 w-4" />
            <span>Create Vendor Review</span>
          </button>
          <button
            type="button"
            onClick={() => void openModal()}
            className="inline-flex items-center justify-center gap-2 px-8 py-3.5 text-sm transition-opacity hover:opacity-70"
            style={{ border: '1px solid var(--line)', color: 'var(--text-2)' }}
          >
            Open Existing Review
          </button>
        </div>
      </div>

      <VendorReviewCreateDialog
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        onCreated={(project) => {
          startTransition(() => {
            router.push(project.workspace_url || `/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`);
          });
        }}
      />

      <AnimatePresence>
        {modalOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 backdrop-blur-sm"
              style={{ background: 'rgba(0,0,0,0.55)' }}
              onClick={() => setModalOpen(false)}
            />
            <motion.div
              key="modal-wrapper"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              onClick={() => setModalOpen(false)}
            >
              <div
                className="w-full max-w-lg text-left"
                style={{ background: 'var(--bg-1)', border: '1px solid var(--line)' }}
                onClick={(e) => e.stopPropagation()}
              >
                <div
                  className="flex items-center justify-between px-5 py-4"
                  style={{ borderBottom: '1px solid var(--line)' }}
                >
                  <div
                    className="text-[11px] uppercase tracking-[0.22em]"
                    style={{ color: 'var(--text-3)' }}
                  >
                    Saved Reviews
                  </div>
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="transition-colors"
                    style={{ color: 'var(--text-3)' }}
                    onMouseEnter={e => (e.currentTarget.style.color = 'var(--text)')}
                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="px-5 pb-3 pt-4" style={{ borderBottom: '1px solid var(--line)' }}>
                  <div
                    className="flex items-center gap-3 px-4 py-2.5"
                    style={{ border: '1px solid var(--line)', background: 'var(--bg-2)' }}
                  >
                    <Search className="h-4 w-4 shrink-0" style={{ color: 'var(--text-3)' }} />
                    <input
                      ref={searchRef}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search reviews..."
                      className="flex-1 bg-transparent text-sm outline-none"
                      style={{ color: 'var(--text)' }}
                    />
                  </div>
                </div>

                <div className="max-h-[360px] overflow-y-auto">
                  {loadingProjects ? (
                    <div className="flex items-center gap-3 px-5 py-8 text-sm" style={{ color: 'var(--text-2)' }}>
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      <span>Loading...</span>
                    </div>
                  ) : filtered.length ? (
                    filtered.map((project) => (
                      <Link
                        key={project.project_id}
                        href={`/vendor-reviews/${project.vendor_review_id || project.project_id}/dashboard`}
                        onClick={() => setModalOpen(false)}
                        className="group flex items-center justify-between gap-4 px-5 py-4 transition-colors"
                        style={{ borderBottom: '1px solid var(--line)' }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-2)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium" style={{ color: 'var(--text)' }}>{project.vendor_name || project.name}</div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: 'var(--text-3)' }}>
                            <span>{statusLabel(project.status)}</span>
                            {project.document_filename && (
                              <span className="truncate">{project.document_filename}</span>
                            )}
                            <span>{formatRelativeDate(project.last_activity_at)}</span>
                          </div>
                        </div>
                        <ArrowUpRight
                          className="h-4 w-4 shrink-0 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                          style={{ color: 'var(--text-3)' }}
                        />
                      </Link>
                    ))
                  ) : (
                    <div className="px-5 py-8 text-sm" style={{ color: 'var(--text-3)' }}>
                      {search ? "No matching reviews." : "No saved reviews yet."}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </section>
  );
}
