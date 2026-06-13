from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..base import AgentTool


class _EmptyInput(BaseModel):
    pass


class ApprovalPackToolset:
    def __init__(
        self,
        *,
        vendor_context: dict[str, Any],
        findings: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> None:
        self._vendor_context = vendor_context
        self._findings = findings
        self._evidence = evidence

    def as_tools(self) -> list[AgentTool]:
        return [
            AgentTool(
                name="get_vendor_context",
                description="Return the vendor review context that frames recommendation language and follow-up questions.",
                input_model=_EmptyInput,
                handler=self.get_vendor_context,
            ),
            AgentTool(
                name="get_review_findings",
                description="Return the validated findings, risks, and weak clauses from the completed review.",
                input_model=_EmptyInput,
                handler=self.get_review_findings,
            ),
            AgentTool(
                name="get_evidence_appendix",
                description="Return the evidence appendix rows already validated by backend review processing.",
                input_model=_EmptyInput,
                handler=self.get_evidence_appendix,
            ),
        ]

    def get_vendor_context(self, _: _EmptyInput) -> dict[str, Any]:
        return self._vendor_context

    def get_review_findings(self, _: _EmptyInput) -> list[dict[str, Any]]:
        return self._findings

    def get_evidence_appendix(self, _: _EmptyInput) -> list[dict[str, Any]]:
        return self._evidence
