from __future__ import annotations

from pathlib import Path

from upload_api.config import Settings

from .schemas import AgentLoopConfig, AgentPromptSpec


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def criteria_prompt_spec(settings: Settings) -> AgentPromptSpec:
    return AgentPromptSpec(
        prompt_path=_PROMPTS_DIR / "criteria_agent_v1.md",
        loop_config=AgentLoopConfig(
            agent_name="criteria_agent",
            agent_role="criteria",
            agent_version="v1",
            prompt_version="criteria_agent_v1",
            model_name=settings.gemini_checklist_model,
            max_tool_calls=settings.agent_default_max_tool_calls,
            output_type="criteria_draft",
            output_schema_version="v2",
        ),
    )


def criteria_research_prompt_spec(settings: Settings) -> AgentPromptSpec:
    return AgentPromptSpec(
        prompt_path=_PROMPTS_DIR / "criteria_research_agent_v1.md",
        loop_config=AgentLoopConfig(
            agent_name="criteria_research_agent",
            agent_role="criteria_research",
            agent_version="v1",
            prompt_version="criteria_research_agent_v1",
            model_name=settings.gemini_checklist_model,
            max_tool_calls=settings.agent_criteria_research_max_tool_calls,
            output_type="criteria_research",
            output_schema_version="v1",
        ),
    )


def review_prompt_spec(settings: Settings) -> AgentPromptSpec:
    return AgentPromptSpec(
        prompt_path=_PROMPTS_DIR / "review_agent_v1.md",
        loop_config=AgentLoopConfig(
            agent_name="review_agent",
            agent_role="review",
            agent_version="v1",
            prompt_version="review_agent_v1",
            model_name=settings.gemini_review_model,
            max_tool_calls=settings.agent_default_max_tool_calls,
            output_type="criterion_assessment",
            output_schema_version="v2",
        ),
    )


def approval_pack_prompt_spec(settings: Settings) -> AgentPromptSpec:
    return AgentPromptSpec(
        prompt_path=_PROMPTS_DIR / "approval_pack_agent_v1.md",
        loop_config=AgentLoopConfig(
            agent_name="approval_pack_agent",
            agent_role="approval_pack",
            agent_version="v1",
            prompt_version="approval_pack_agent_v1",
            model_name=settings.gemini_approval_pack_model or settings.gemini_review_model,
            max_tool_calls=settings.agent_default_max_tool_calls,
            output_type="approval_pack_draft",
            output_schema_version="v1",
        ),
    )
