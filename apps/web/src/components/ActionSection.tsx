"use client";

import Link from "next/link";
import { startTransition, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, LoaderCircle, Plus, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { createProject, listProjects, type ProjectSummary } from "@/lib/uploadApi";

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
  const [creating, setCreating] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
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

  async function handleCreate() {
    if (creating) return;
    setCreating(true);
    try {
      const project = await createProject();
      startTransition(() => {
        router.push(project.workspace_url || `/projects/${project.project_id}`);
      });
    } finally {
      setCreating(false);
    }
  }

  async function openModal() {
    setSearch("");
    setModalOpen(true);
    setLoadingProjects(true);
    try {
      const items = await listProjects();
      setProjects(items);
    } finally {
      setLoadingProjects(false);
    }
  }

  const filtered = projects.filter((p) => {
    const q = search.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      (p.document_filename ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <section className="relative z-20 w-full flex flex-col items-center text-center px-6 pb-24">
      {/* Ambient bloom matching the page's light sources */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden">
        <div className="w-[90vw] h-[70vh] bg-[radial-gradient(ellipse,rgba(99,102,241,0.11),transparent_60%)]" />
        <div className="absolute w-[50vw] h-[40vh] bg-[radial-gradient(ellipse,rgba(139,92,246,0.08),transparent_55%)] translate-y-8" />
      </div>

      {/* Vertical rule — visual breath between scroll sections and CTA */}
      <div className="w-px h-12 bg-gradient-to-b from-transparent via-white/15 to-transparent mb-10" />

      <div className="relative max-w-2xl w-full">
        <p className="mb-5 text-[10px] uppercase tracking-[0.3em] text-white/45">
          Begin
        </p>
        <h2
          className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight"
          style={{
            background: 'linear-gradient(150deg, #ffffff 0%, rgba(210,210,255,0.88) 50%, rgba(255,255,255,0.65) 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          Start a new analysis.
        </h2>
        <p className="mt-5 text-sm leading-7 text-white/55 max-w-sm mx-auto">
          One project per DPA. Upload, parse, and generate a compliance checklist — all in one place.
        </p>

        <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={creating}
            className="inline-flex items-center justify-center gap-2 bg-white px-8 py-3.5 text-sm font-medium text-black transition-all disabled:opacity-70 hover:bg-white/90"
          >
            {creating ? (
              <>
                <LoaderCircle className="h-4 w-4 animate-spin" />
                <span>Creating...</span>
              </>
            ) : (
              <>
                <Plus className="h-4 w-4" />
                <span>Create New Analysis</span>
              </>
            )}
          </button>
          <button
            type="button"
            onClick={() => void openModal()}
            className="inline-flex items-center justify-center gap-2 border border-white/15 px-8 py-3.5 text-sm text-white/65 transition-colors hover:bg-white/5 hover:text-white/85"
          >
            Open Existing Analysis
          </button>
        </div>
      </div>

      <AnimatePresence>
        {modalOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
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
                className="w-full max-w-lg border border-white/12 bg-[rgba(8,8,26,0.97)]"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                  <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">Saved Analyses</div>
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="text-white/40 transition-colors hover:text-white/80"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="border-b border-white/10 px-5 pb-3 pt-4">
                  <div className="flex items-center gap-3 border border-white/10 bg-black/25 px-4 py-2.5">
                    <Search className="h-4 w-4 shrink-0 text-white/35" />
                    <input
                      ref={searchRef}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search projects..."
                      className="flex-1 bg-transparent text-sm text-white outline-none placeholder:text-white/30"
                    />
                  </div>
                </div>

                <div className="max-h-[360px] overflow-y-auto">
                  {loadingProjects ? (
                    <div className="flex items-center gap-3 px-5 py-8 text-sm text-white/50">
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      <span>Loading...</span>
                    </div>
                  ) : filtered.length ? (
                    filtered.map((project) => (
                      <Link
                        key={project.project_id}
                        href={`/projects/${project.project_id}`}
                        onClick={() => setModalOpen(false)}
                        className="group flex items-center justify-between gap-4 border-b border-white/8 px-5 py-4 transition-colors hover:bg-white/[0.03]"
                      >
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-white/88">{project.name}</div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-white/38">
                            <span>{statusLabel(project.status)}</span>
                            {project.document_filename && (
                              <span className="truncate">{project.document_filename}</span>
                            )}
                            <span>{formatRelativeDate(project.last_activity_at)}</span>
                          </div>
                        </div>
                        <ArrowUpRight className="h-4 w-4 shrink-0 text-white/35 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-white/65" />
                      </Link>
                    ))
                  ) : (
                    <div className="px-5 py-8 text-sm text-white/40">
                      {search ? "No matching projects." : "No saved projects yet."}
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
