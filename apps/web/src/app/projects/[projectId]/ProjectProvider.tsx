"use client";

import { createContext, useContext, useEffect, useEffectEvent, useRef, useState } from "react";
import {
  analysisRunEventsUrl,
  type AnalysisRunStatus,
  checklistDraftEventsUrl,
  getProject,
  listProjects,
  listReferenceSources,
  type ChecklistDraftStatus,
  type ProjectDetail,
  type ProjectSummary,
  type ReferenceSource,
  type UploadJobStatus,
  uploadEventsUrl,
} from "@/lib/uploadApi";

interface ProjectContextValue {
  projectId: string;
  loading: boolean;
  projects: ProjectSummary[];
  detail: ProjectDetail | null;
  sources: ReferenceSource[];
  workspaceError: string | null;
  uploadError: string | null;
  setUploadError: (error: string | null) => void;
  setWorkspaceError: (error: string | null) => void;
  refreshProject: (showError?: boolean) => Promise<void>;
  refreshSidebar: () => Promise<void>;
  setDetail: React.Dispatch<React.SetStateAction<ProjectDetail | null>>;
  connectUploadSocket: (jobId: string) => void;
  connectChecklistSocket: (draftId: string) => void;
  connectAnalysisSocket: (runId: string) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

function hasSocketError(payload: unknown): payload is { error?: string } {
  return !!payload && typeof payload === "object" && "error" in payload;
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (!context) throw new Error("useProject must be used within a ProjectProvider");
  return context;
}

export function ProjectProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: React.ReactNode;
}) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [sources, setSources] = useState<ReferenceSource[]>([]);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const uploadSocketRef = useRef<WebSocket | null>(null);
  const uploadPingRef = useRef<number | null>(null);
  const checklistSocketRef = useRef<WebSocket | null>(null);
  const checklistPingRef = useRef<number | null>(null);
  const analysisSocketRef = useRef<WebSocket | null>(null);
  const analysisPingRef = useRef<number | null>(null);

  const parseJob = detail?.parse_job;
  const checklistDraft = detail?.checklist_draft;
  const analysisRun = detail?.analysis_run;

  const pollProjectRefresh = useEffectEvent(() => {
    void refreshProject(false);
  });

  async function refreshSidebar() {
    try {
      const items = await listProjects();
      setProjects(items);
    } catch {
      // Background refresh, ignore errors
    }
  }

  async function refreshProject(showError = true) {
    if (!projectId) return;
    try {
      const result = await getProject(projectId);
      setDetail(result);
    } catch (error) {
      if (showError) {
        setWorkspaceError(error instanceof Error ? error.message : "Failed to load project.");
      }
    }
  }

  // Initial Data Load
  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!projectId) return;
      setLoading(true);
      setWorkspaceError(null);
      try {
        const [projectDetail, projectList, referenceSources] = await Promise.all([
          getProject(projectId),
          listProjects(),
          listReferenceSources(),
        ]);
        if (cancelled) return;
        setDetail(projectDetail);
        setProjects(projectList);
        setSources(referenceSources);
      } catch (error) {
        if (!cancelled) setWorkspaceError(error instanceof Error ? error.message : "Failed to load project workspace.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Cleanup WebSockets on unmount
  useEffect(() => {
    return () => {
      closeUploadSocket();
      closeChecklistSocket();
      closeAnalysisSocket();
    };
  }, []);

  // Polling fallback when jobs are active
  useEffect(() => {
    if (!parseJob && !checklistDraft && !analysisRun) return;
    const parseActive = parseJob && !["COMPLETED", "FAILED"].includes(parseJob.status);
    const checklistActive = checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status);
    const analysisActive = analysisRun && !["COMPLETED", "FAILED"].includes(analysisRun.status);
    if (!parseActive && !checklistActive && !analysisActive) return;

    const timer = window.setInterval(() => {
      pollProjectRefresh();
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [parseJob, checklistDraft, analysisRun]);

  // Sync Errors
  useEffect(() => {
    if (parseJob?.status === "FAILED" && parseJob.error_message) {
      setUploadError(parseJob.error_message);
    }
  }, [parseJob?.status, parseJob?.error_message]);

  useEffect(() => {
    if (checklistDraft?.status === "FAILED" && checklistDraft.error_message) {
      setWorkspaceError(checklistDraft.error_message);
    }
  }, [checklistDraft?.status, checklistDraft?.error_message]);

  useEffect(() => {
    if (analysisRun?.status === "FAILED" && analysisRun.error_message) {
      setWorkspaceError(analysisRun.error_message);
    }
  }, [analysisRun?.status, analysisRun?.error_message]);

  // Auto-connect websockets if jobs are active (survives page refresh)
  useEffect(() => {
    if (parseJob && !["COMPLETED", "FAILED"].includes(parseJob.status)) {
      if (!uploadSocketRef.current || uploadSocketRef.current.readyState === WebSocket.CLOSED) {
        connectUploadSocket(parseJob.job_id);
      }
    }
  }, [parseJob?.job_id, parseJob?.status]);

  useEffect(() => {
    if (checklistDraft && !["COMPLETED", "FAILED"].includes(checklistDraft.status)) {
      if (!checklistSocketRef.current || checklistSocketRef.current.readyState === WebSocket.CLOSED) {
        connectChecklistSocket(checklistDraft.checklist_draft_id);
      }
    }
  }, [checklistDraft?.checklist_draft_id, checklistDraft?.status]);

  useEffect(() => {
    if (analysisRun && !["COMPLETED", "FAILED"].includes(analysisRun.status)) {
      if (!analysisSocketRef.current || analysisSocketRef.current.readyState === WebSocket.CLOSED) {
        connectAnalysisSocket(analysisRun.analysis_run_id);
      }
    }
  }, [analysisRun?.analysis_run_id, analysisRun?.status]);

  function closeUploadSocket() {
    if (uploadPingRef.current) {
      window.clearInterval(uploadPingRef.current);
      uploadPingRef.current = null;
    }
    if (uploadSocketRef.current) {
      uploadSocketRef.current.close();
      uploadSocketRef.current = null;
    }
  }

  function closeChecklistSocket() {
    if (checklistPingRef.current) {
      window.clearInterval(checklistPingRef.current);
      checklistPingRef.current = null;
    }
    if (checklistSocketRef.current) {
      checklistSocketRef.current.close();
      checklistSocketRef.current = null;
    }
  }

  function closeAnalysisSocket() {
    if (analysisPingRef.current) {
      window.clearInterval(analysisPingRef.current);
      analysisPingRef.current = null;
    }
    if (analysisSocketRef.current) {
      analysisSocketRef.current.close();
      analysisSocketRef.current = null;
    }
  }

  function connectUploadSocket(jobId: string) {
    closeUploadSocket();
    const ws = new WebSocket(uploadEventsUrl(jobId));
    uploadSocketRef.current = ws;

    ws.onopen = () => {
      uploadPingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 10000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as UploadJobStatus | { error?: string };
        if (hasSocketError(payload) && payload.error) {
          setUploadError(payload.error);
          return;
        }
        const snapshot = payload as UploadJobStatus;
        setDetail((prev) => (prev ? { ...prev, parse_job: snapshot } : prev));
        if (snapshot.status === "FAILED") {
          setUploadError(snapshot.error_message || "Document processing failed.");
        }
        if (snapshot.status === "COMPLETED" || snapshot.status === "FAILED") {
          closeUploadSocket();
          void Promise.all([refreshProject(false), refreshSidebar()]);
        }
      } catch {
        // invalid event
      }
    };

    ws.onclose = () => {
      closeUploadSocket();
    };
    ws.onerror = () => {
      closeUploadSocket();
    };
  }

  function connectChecklistSocket(draftId: string) {
    closeChecklistSocket();
    const ws = new WebSocket(checklistDraftEventsUrl(draftId));
    checklistSocketRef.current = ws;

    ws.onopen = () => {
      checklistPingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ChecklistDraftStatus | { error?: string };
        if (hasSocketError(payload) && payload.error) {
          setWorkspaceError(payload.error);
          return;
        }
        const snapshot = payload as ChecklistDraftStatus;
        setDetail((prev) => (prev ? { ...prev, checklist_draft: snapshot } : prev));
        if (snapshot.status === "FAILED") {
          setWorkspaceError(snapshot.error_message || "Checklist generation failed.");
        }
        if (snapshot.status === "COMPLETED" || snapshot.status === "FAILED") {
          closeChecklistSocket();
          void Promise.all([refreshProject(false), refreshSidebar()]);
        }
      } catch {
        // invalid event
      }
    };

    ws.onclose = () => {
      closeChecklistSocket();
    };
    ws.onerror = () => {
      closeChecklistSocket();
    };
  }

  function connectAnalysisSocket(runId: string) {
    closeAnalysisSocket();
    const ws = new WebSocket(analysisRunEventsUrl(runId));
    analysisSocketRef.current = ws;

    ws.onopen = () => {
      analysisPingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as AnalysisRunStatus | { error?: string };
        if (hasSocketError(payload) && payload.error) {
          setWorkspaceError(payload.error);
          return;
        }
        const snapshot = payload as AnalysisRunStatus;
        setDetail((prev) => (prev ? { ...prev, analysis_run: snapshot } : prev));
        if (snapshot.status === "FAILED") {
          setWorkspaceError(snapshot.error_message || "Final review failed.");
        }
        if (snapshot.status === "COMPLETED" || snapshot.status === "FAILED") {
          closeAnalysisSocket();
          void Promise.all([refreshProject(false), refreshSidebar()]);
        }
      } catch {
        // invalid event
      }
    };

    ws.onclose = () => {
      closeAnalysisSocket();
    };
    ws.onerror = () => {
      closeAnalysisSocket();
    };
  }

  const value: ProjectContextValue = {
    projectId,
    loading,
    projects,
    detail,
    sources,
    workspaceError,
    uploadError,
    setUploadError,
    setWorkspaceError,
    refreshProject,
    refreshSidebar,
    setDetail,
    connectUploadSocket,
    connectChecklistSocket,
    connectAnalysisSocket,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}
