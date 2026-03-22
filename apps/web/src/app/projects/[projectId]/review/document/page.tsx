"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, LoaderCircle, TriangleAlert } from "lucide-react";
import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import { getDocumentProxyUrl } from "@/lib/uploadApi";
import { useProject } from "../../ProjectProvider";

GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const VIEWPORT_SCALE = 1.35;

export default function ReviewDocumentViewerPage() {
  const searchParams = useSearchParams();
  const { projectId, detail } = useProject();
  const document = detail?.document;
  const requestedPageParam = Number(searchParams.get("page") || "1");
  const requestedPage = Number.isFinite(requestedPageParam) && requestedPageParam > 0 ? Math.floor(requestedPageParam) : 1;

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(requestedPage);

  const proxyUrl = useMemo(() => {
    if (!document?.document_id) return null;
    return getDocumentProxyUrl(document.document_id);
  }, [document?.document_id]);

  useEffect(() => {
    setCurrentPage(requestedPage);
  }, [requestedPage]);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: ReturnType<typeof getDocument> | null = null;
    let pdfDocument: Awaited<ReturnType<typeof getDocument>["promise"]> | null = null;
    let renderTask: { cancel: () => void; promise: Promise<void> } | null = null;

    async function renderPdfPage() {
      if (!proxyUrl || !canvasRef.current) {
        if (!cancelled) {
          setError("Project document is unavailable.");
          setLoading(false);
        }
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const response = await fetch(proxyUrl, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Failed to load document (${response.status})`);
        }

        const buffer = await response.arrayBuffer();
        if (cancelled) return;

        loadingTask = getDocument({ data: new Uint8Array(buffer) });
        pdfDocument = await loadingTask.promise;
        if (cancelled) return;

        setPageCount(pdfDocument.numPages);
        const safePage = Math.min(Math.max(currentPage, 1), pdfDocument.numPages);
        if (safePage !== currentPage) {
          setCurrentPage(safePage);
        }

        const page = await pdfDocument.getPage(safePage);
        if (cancelled || !canvasRef.current) return;

        const viewport = page.getViewport({ scale: VIEWPORT_SCALE });
        const outputScale = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");
        if (!context) {
          throw new Error("Canvas rendering is unavailable.");
        }

        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;

        context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
        renderTask = page.render({ canvasContext: context, viewport, canvas });
        await renderTask.promise;
        if (!cancelled) {
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to render document.");
          setLoading(false);
        }
      } finally {
        await pdfDocument?.destroy();
      }
    }

    void renderPdfPage();

    return () => {
      cancelled = true;
      renderTask?.cancel();
      loadingTask?.destroy();
    };
  }, [proxyUrl, currentPage]);

  if (!document) {
    return (
      <section className="border px-6 py-8" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)', color: 'var(--text-2)' }}>
        No project document was found.
      </section>
    );
  }

  const canGoPrev = currentPage > 1;
  const canGoNext = pageCount !== null && currentPage < pageCount;

  return (
    <div className="grid gap-5 pb-6">
      <section className="border px-6 py-5" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-3)' }}>DPA Viewer</div>
            <h2 className="mt-2 text-2xl font-semibold" style={{ color: 'var(--text)' }}>{document.filename}</h2>
            <div className="mt-2 text-sm" style={{ color: 'var(--text-2)' }}>
              Page {currentPage}
              {pageCount ? ` of ${pageCount}` : ""}
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => canGoPrev && setCurrentPage((page) => Math.max(1, page - 1))}
              disabled={!canGoPrev}
              className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </button>
            <button
              type="button"
              onClick={() => canGoNext && setCurrentPage((page) => page + 1)}
              disabled={!canGoNext}
              className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
            <Link
              href={`/projects/${projectId}/review/report`}
              className="inline-flex items-center gap-2 border px-4 py-2.5 text-sm transition-colors"
              style={{ borderColor: 'var(--line)', background: 'var(--bg-2)', color: 'var(--text-2)' }}
            >
              Back to Report
            </Link>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="flex items-center gap-3 border p-6" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)', color: 'var(--text-2)' }}>
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Rendering PDF page...
        </div>
      ) : null}

      {error ? (
        <div className="flex gap-3 border border-red-400/20 bg-red-400/6 p-4 text-sm text-red-100/85">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{error}</div>
        </div>
      ) : null}

      <section className="overflow-auto border px-6 py-6" style={{ borderColor: 'var(--line)', background: 'var(--bg-1)' }}>
        <div className="mx-auto w-fit bg-white p-3 shadow-[0_20px_80px_rgba(0,0,0,0.45)]">
          <canvas ref={canvasRef} />
        </div>
      </section>
    </div>
  );
}
