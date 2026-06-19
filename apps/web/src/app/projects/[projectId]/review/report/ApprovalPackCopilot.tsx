"use client";

import { FormEvent, startTransition, useEffect, useEffectEvent, useRef, useState } from "react";
import {
  Bot,
  Check,
  ChevronDown,
  CircleDashed,
  FileSearch,
  LoaderCircle,
  MessageSquarePlus,
  PanelRight,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { CheckerPanel } from "@/components/checker-ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ApiError,
  applyApprovalPackRevision,
  copilotThreadEventsUrl,
  createCopilotThread,
  listCopilotMessages,
  listCopilotThreads,
  rejectApprovalPackRevision,
  sendCopilotMessage,
  type ApprovalPackRevision,
  type CopilotEvent,
  type CopilotMessage,
  type CopilotSource,
  type CopilotThread,
  type CopilotToolActivity,
} from "@/lib/uploadApi";

type ThreadState = "loading" | "ready" | "unavailable" | "error";

function formatThreadTitle(thread: CopilotThread, index: number) {
  return thread.title?.trim() || `Thread ${index + 1}`;
}

function formatSource(source: CopilotSource) {
  const label = source.label || source.title || source.source_id || "Source";
  return source.page ? `${label} p.${source.page}` : label;
}

function sortMessages(messages: CopilotMessage[]) {
  return [...messages].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
}

function mergeMessage(messages: CopilotMessage[], next: CopilotMessage) {
  const index = messages.findIndex((message) => message.message_id === next.message_id);
  if (index === -1) return sortMessages([...messages, next]);
  const copy = [...messages];
  copy[index] = { ...copy[index], ...next };
  return sortMessages(copy);
}

function normalizeActivity(payload: CopilotEvent): CopilotToolActivity | null {
  const activity = payload.activity ?? payload.tool_activity;
  if (activity?.label) return activity;
  if (payload.type?.includes("tool") || payload.event?.includes("tool")) {
    return {
      activity_id: payload.message_id ?? null,
      label: payload.content || payload.status || "Using project context",
      status: payload.status || "running",
    };
  }
  return null;
}

function isUnavailable(error: unknown) {
  return error instanceof ApiError && [404, 405, 501].includes(error.status);
}

function SourceChips({ sources }: { sources?: CopilotSource[] }) {
  if (!sources?.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {sources.slice(0, 6).map((source, index) => (
        <Badge
          key={`${source.source_id || source.title}-${index}`}
          variant="outline"
          className="max-w-full rounded-full bg-background text-[11px] text-muted-foreground"
          title={source.excerpt || source.title}
        >
          <FileSearch data-icon="inline-start" className="h-3 w-3 shrink-0" />
          <span className="truncate">{formatSource(source)}</span>
        </Badge>
      ))}
    </div>
  );
}

function ToolRows({ rows }: { rows: CopilotToolActivity[] }) {
  if (!rows.length) return null;
  return (
    <div className="mb-3 grid gap-1.5">
      {rows.slice(-4).map((row, index) => (
        <ToolRow
          key={row.activity_id || `${row.label}-${index}`}
          row={row}
        />
      ))}
    </div>
  );
}

function ToolRow({ row }: { row: CopilotToolActivity }) {
  const [open, setOpen] = useState(false);
  const hasDetail = !!row.detail;
  const pending = row.status === "running" || row.status === "queued";

  return (
    <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-muted-foreground">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((value) => !value)}
        aria-expanded={hasDetail ? open : undefined}
        aria-disabled={!hasDetail}
        className={`flex w-full items-center justify-between gap-3 text-left text-xs ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="flex min-w-0 items-center gap-2">
          {pending ? (
            <CircleDashed className="h-3.5 w-3.5 shrink-0 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5 shrink-0" />
          )}
          <span className="truncate">{row.label}</span>
        </span>
        {hasDetail ? (
          <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
        ) : null}
      </button>
      {hasDetail && open ? (
        <p className="mt-2 border-t border-border pt-2 text-xs leading-5 text-muted-foreground">
          {row.detail}
        </p>
      ) : null}
    </div>
  );
}

function RevisionCard({
  revision,
  onApply,
  onReject,
  busy,
}: {
  revision: ApprovalPackRevision;
  onApply: (revisionId: string) => void;
  onReject: (revisionId: string) => void;
  busy: boolean;
}) {
  const terminal = ["approved", "applied", "rejected"].includes(revision.status);

  return (
    <Card className="mt-3 bg-background">
      <CardContent>
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--accent)" }} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{revision.summary}</div>
          {revision.reason ? <p className="mt-1 text-xs leading-5" style={{ color: "var(--text-2)" }}>{revision.reason}</p> : null}
          <div className="mt-2 text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--text-3)" }}>
            Revision {revision.status.replaceAll("_", " ")}
          </div>
        </div>
      </div>
      {!terminal ? (
        <div className="mt-3 flex gap-2">
          <Button
            type="button"
            onClick={() => onApply(revision.revision_id)}
            disabled={busy}
            size="sm"
            className="bg-[var(--success)] text-background hover:opacity-90"
          >
            {busy ? <LoaderCircle data-icon="inline-start" className="h-3.5 w-3.5 animate-spin" /> : <Check data-icon="inline-start" className="h-3.5 w-3.5" />}
            Approve
          </Button>
          <Button
            type="button"
            onClick={() => onReject(revision.revision_id)}
            disabled={busy}
            variant="outline"
            size="sm"
            className="rounded-lg"
          >
            <X data-icon="inline-start" className="h-3.5 w-3.5" />
            Reject
          </Button>
        </div>
      ) : null}
      </CardContent>
    </Card>
  );
}

function MessageBubble({
  message,
  onApplyRevision,
  onRejectRevision,
  revisionBusyId,
}: {
  message: CopilotMessage;
  onApplyRevision: (revisionId: string) => void;
  onRejectRevision: (revisionId: string) => void;
  revisionBusyId: string | null;
}) {
  const isUser = message.role === "user";
  const sources = message.citations?.length ? message.citations : message.sources;

  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[92%] rounded-lg border px-4 py-3 shadow-sm ${isUser ? "rounded-br-sm" : "rounded-bl-sm"}`}
        style={{
          borderColor: isUser ? "var(--invert)" : "var(--line)",
          background: isUser ? "var(--invert)" : "var(--bg-1)",
          color: isUser ? "var(--invert-fg)" : "var(--text)",
        }}
      >
        {!isUser ? (
          <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.16em]" style={{ color: "var(--text-3)" }}>
            <Bot className="h-3.5 w-3.5" />
            Copilot
          </div>
        ) : null}
        {!isUser ? <ToolRows rows={message.tool_activities || []} /> : null}
        <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        <SourceChips sources={sources} />
        {message.revisions?.map((revision, index) => (
          <RevisionCard
            key={`${revision.revision_id}-${index}`}
            revision={revision}
            onApply={onApplyRevision}
            onReject={onRejectRevision}
            busy={revisionBusyId === revision.revision_id}
          />
        ))}
      </div>
    </article>
  );
}

export function ApprovalPackCopilot({
  projectId,
  onClose,
  className,
}: {
  projectId: string;
  onClose?: () => void;
  className?: string;
}) {
  const [threadState, setThreadState] = useState<ThreadState>("loading");
  const [threads, setThreads] = useState<CopilotThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [liveActivities, setLiveActivities] = useState<CopilotToolActivity[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [creatingThread, setCreatingThread] = useState(false);
  const [revisionBusyId, setRevisionBusyId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<number | null>(null);

  const handleSocketPayload = useEffectEvent((payload: CopilotEvent) => {
    if (payload.error) {
      setError(payload.error);
      return;
    }
    if (payload.activity || payload.tool_activity || payload.type?.includes("tool") || payload.event?.includes("tool")) {
      const activity = normalizeActivity(payload);
      if (activity) setLiveActivities((current) => [...current, activity]);
    }
    if (payload.message) {
      startTransition(() => {
        setMessages((current) => mergeMessage(current, payload.message as CopilotMessage));
      });
      return;
    }
    if (payload.delta || payload.content) {
      const id = payload.message_id || "streaming-assistant";
      const delta = payload.delta || payload.content || "";
      startTransition(() => {
        setMessages((current) => {
          const existing = current.find((message) => message.message_id === id);
          if (existing) {
            return mergeMessage(current, { ...existing, content: `${existing.content}${delta}`, status: "streaming" });
          }
          return mergeMessage(current, {
            message_id: id,
            thread_id: payload.thread_id || activeThreadId || "",
            role: payload.role || "assistant",
            content: delta,
            status: "streaming",
            created_at: new Date().toISOString(),
          });
        });
      });
    }
    if (payload.revision) {
      setMessages((current) => {
        const copy = [...current];
        const lastAssistantIndex = copy.findLastIndex((message) => message.role === "assistant");
        if (lastAssistantIndex === -1) return current;
        const target = copy[lastAssistantIndex];
        copy[lastAssistantIndex] = { ...target, revisions: [...(target.revisions || []), payload.revision as ApprovalPackRevision] };
        return copy;
      });
    }
  });

  useEffect(() => {
    let cancelled = false;

    async function loadThreads() {
      setThreadState("loading");
      setError(null);
      try {
        const loadedThreads = await listCopilotThreads(projectId);
        if (cancelled) return;
        setThreads(loadedThreads);
        setActiveThreadId(loadedThreads[0]?.thread_id ?? null);
        setThreadState("ready");
      } catch (loadError) {
        if (cancelled) return;
        if (isUnavailable(loadError)) {
          setThreadState("unavailable");
          setError("Copilot backend routes are not available yet.");
        } else {
          setThreadState("error");
          setError(loadError instanceof Error ? loadError.message : "Failed to load copilot threads.");
        }
      }
    }

    void loadThreads();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!activeThreadId) {
      setMessages([]);
      return;
    }
    const threadId = activeThreadId;
    let cancelled = false;

    async function loadMessages() {
      setError(null);
      setLiveActivities([]);
      try {
        const loadedMessages = await listCopilotMessages(threadId);
        if (!cancelled) setMessages(sortMessages(loadedMessages));
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Failed to load copilot messages.");
      }
    }

    void loadMessages();
    return () => {
      cancelled = true;
    };
  }, [activeThreadId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, liveActivities.length]);

  useEffect(() => {
    if (!activeThreadId || threadState !== "ready") return;
    if (pingRef.current) window.clearInterval(pingRef.current);
    if (socketRef.current) socketRef.current.close();

    const ws = new WebSocket(copilotThreadEventsUrl(activeThreadId));
    socketRef.current = ws;
    ws.onopen = () => {
      pingRef.current = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 15000);
    };
    ws.onmessage = (event) => {
      try {
        handleSocketPayload(JSON.parse(event.data) as CopilotEvent);
      } catch {
        // Ignore malformed progress events.
      }
    };
    ws.onerror = () => {
      if (threadState === "ready") setError("Live copilot updates are unavailable. Messages can still be refreshed.");
    };

    return () => {
      if (pingRef.current) {
        window.clearInterval(pingRef.current);
        pingRef.current = null;
      }
      ws.close();
    };
  }, [activeThreadId, threadState]);

  async function handleNewThread() {
    setCreatingThread(true);
    setError(null);
    try {
      const nextThread = await createCopilotThread(projectId);
      setThreads((current) => [nextThread, ...current.filter((thread) => thread.thread_id !== nextThread.thread_id)]);
      setActiveThreadId(nextThread.thread_id);
      setMessages([]);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Failed to create a new copilot thread.");
    } finally {
      setCreatingThread(false);
    }
  }

  async function ensureThread() {
    if (activeThreadId) return activeThreadId;
    const nextThread = await createCopilotThread(projectId);
    setThreads((current) => [nextThread, ...current]);
    setActiveThreadId(nextThread.thread_id);
    return nextThread.thread_id;
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending || threadState !== "ready") return;
    setSending(true);
    setError(null);
    setDraft("");
    try {
      const threadId = await ensureThread();
      const optimisticMessageId = `local-${Date.now()}`;
      const optimisticMessage: CopilotMessage = {
        message_id: optimisticMessageId,
        thread_id: threadId,
        role: "user",
        content,
        status: "completed",
        created_at: new Date().toISOString(),
      };
      setMessages((current) => mergeMessage(current, optimisticMessage));
      const response = await sendCopilotMessage(threadId, content);
      if (response.user_message) {
        setMessages((current) =>
          mergeMessage(
            current.filter((message) => message.message_id !== optimisticMessageId),
            response.user_message as CopilotMessage,
          ),
        );
      }
      if (response.message) setMessages((current) => mergeMessage(current, response.message as CopilotMessage));
      if (response.assistant_message) setMessages((current) => mergeMessage(current, response.assistant_message as CopilotMessage));
      if (response.messages?.length) setMessages(sortMessages(response.messages));
      const assistantIncludesRevision = response.assistant_message?.revisions?.some(
        (revision) => revision.revision_id === response.revision?.revision_id,
      );
      if (response.revision && !assistantIncludesRevision) {
        setMessages((current) => {
          const copy = [...current];
          const lastAssistantIndex = copy.findLastIndex((message) => message.role === "assistant");
          if (lastAssistantIndex === -1) return current;
          const target = copy[lastAssistantIndex];
          copy[lastAssistantIndex] = { ...target, revisions: [...(target.revisions || []), response.revision as ApprovalPackRevision] };
          return copy;
        });
      }
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Failed to send message.");
      setDraft(content);
    } finally {
      setSending(false);
    }
  }

  async function updateRevision(revisionId: string, action: "apply" | "reject") {
    setRevisionBusyId(revisionId);
    setError(null);
    try {
      const updated = action === "apply" ? await applyApprovalPackRevision(revisionId) : await rejectApprovalPackRevision(revisionId);
      setMessages((current) =>
        current.map((message) => ({
          ...message,
          revisions: message.revisions?.map((revision) => (revision.revision_id === revisionId ? updated : revision)),
        })),
      );
    } catch (revisionError) {
      setError(revisionError instanceof Error ? revisionError.message : `Failed to ${action} revision.`);
    } finally {
      setRevisionBusyId(null);
    }
  }

  return (
    <section className={cn("flex min-h-[560px] flex-col overflow-hidden rounded-xl border border-border/70 bg-card/95 text-card-foreground shadow-sm", className)}>
      <div className="border-b border-border/70 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              <PanelRight className="h-3.5 w-3.5" />
              Approval Copilot
            </div>
            <p className="mt-2 text-sm leading-5 text-muted-foreground">
              Ask about evidence, rationale, and proposed Approval Pack edits.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              onClick={() => void handleNewThread()}
              disabled={threadState !== "ready" || creatingThread}
              variant="outline"
              size="sm"
            >
              {creatingThread ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <MessageSquarePlus data-icon="inline-start" />}
              New Chat
            </Button>
            {onClose ? (
              <Button type="button" onClick={onClose} aria-label="Close Approval Copilot" variant="ghost" size="icon-sm">
                <X data-icon="inline-start" />
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      {threads.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto border-b border-border/70 p-3">
          {threads.map((thread, index) => (
            <button
              key={`${thread.thread_id}-${index}`}
              type="button"
              onClick={() => setActiveThreadId(thread.thread_id)}
              className={cn(
                "max-w-[180px] shrink-0 rounded-lg border px-3 py-2 text-left text-xs transition-colors",
                activeThreadId === thread.thread_id
                  ? "border-primary/30 bg-primary/10 text-foreground"
                  : "border-border/70 bg-background/70 text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="block truncate">{formatThreadTitle(thread, index)}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col">
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-4">
          {threadState === "loading" ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              Loading copilot...
            </div>
          ) : null}

          {threadState === "unavailable" ? (
            <CheckerPanel className="p-4 text-sm leading-6 text-muted-foreground">
              Copilot is ready on the frontend, but the backend endpoints are not available in this checkout yet.
            </CheckerPanel>
          ) : null}

          {threadState === "error" ? (
            <CheckerPanel className="border-[var(--danger)] bg-[var(--danger-bg)] p-4 text-sm leading-6 text-[var(--danger)]">
              {error || "Failed to load copilot."}
            </CheckerPanel>
          ) : null}

          {threadState === "ready" && !messages.length ? (
            <div className="grid gap-3">
              <CheckerPanel className="bg-background p-4">
                <div className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text)" }}>
                  <Sparkles className="h-4 w-4" />
                  Start with a project question
                </div>
                <p className="mt-2 text-sm leading-6" style={{ color: "var(--text-2)" }}>
                  Try asking why a risk was rated high, where a clause was found, or how to revise the internal memo.
                </p>
              </CheckerPanel>
            </div>
          ) : null}

          {threadState === "ready" ? (
            <div className="grid gap-4">
              {messages.map((message, index) => (
                <MessageBubble
                  key={`${message.message_id}-${index}`}
                  message={message}
                  onApplyRevision={(revisionId) => void updateRevision(revisionId, "apply")}
                  onRejectRevision={(revisionId) => void updateRevision(revisionId, "reject")}
                  revisionBusyId={revisionBusyId}
                />
              ))}
              <ToolRows rows={liveActivities} />
              <div ref={messagesEndRef} />
            </div>
          ) : null}
          </div>
        </ScrollArea>

        {error && threadState === "ready" ? (
          <div className="border-t border-border/70 bg-[var(--danger-bg)] px-4 py-2 text-xs text-[var(--danger)]">
            {error}
          </div>
        ) : null}

        <form onSubmit={(event) => void handleSend(event)} className="border-t border-border/70 bg-background p-3">
          <label className="sr-only" htmlFor="copilot-message">Message copilot</label>
          <div className="flex items-end gap-2">
            <Textarea
              id="copilot-message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={threadState !== "ready" || sending}
              rows={3}
              placeholder={threadState === "ready" ? "Ask about the Approval Pack..." : "Copilot unavailable"}
              className="min-h-20 flex-1 resize-none rounded-lg bg-muted/40 px-3 py-2 text-sm disabled:opacity-60"
            />
            <Button
              type="submit"
              disabled={!draft.trim() || threadState !== "ready" || sending}
              size="icon"
              className="size-10 rounded-lg"
              aria-label="Send copilot message"
            >
              {sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
