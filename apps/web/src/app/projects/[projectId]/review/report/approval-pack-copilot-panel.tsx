"use client";

import { useEffect, useState } from "react";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

import { ApprovalPackCopilot } from "./ApprovalPackCopilot";

function useDesktopRail() {
  const [desktop, setDesktop] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1536px)");
    const update = () => setDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return desktop;
}

export function ApprovalPackCopilotPanel({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const desktop = useDesktopRail();

  if (!open) return null;

  if (desktop) {
    return (
      <aside className="hidden min-h-0 2xl:block">
        <ApprovalPackCopilot
          projectId={projectId}
          onClose={() => onOpenChange(false)}
          className="sticky top-0 h-[calc(100dvh-13rem)]"
        />
      </aside>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" showCloseButton={false} className="w-[min(100vw,420px)] max-w-none gap-0 p-0 sm:max-w-none">
        <SheetTitle className="sr-only">Approval Copilot</SheetTitle>
        <ApprovalPackCopilot
          projectId={projectId}
          onClose={() => onOpenChange(false)}
          className="h-full min-h-0 rounded-none border-0 shadow-none"
        />
      </SheetContent>
    </Sheet>
  );
}
