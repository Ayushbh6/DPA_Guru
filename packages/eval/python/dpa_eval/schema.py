from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalRecord(StrictModel):
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    metric_value: float
    threshold: float
    pass_fail: bool
    evaluated_at: datetime
    notes: str | None = None


class EvalBatch(StrictModel):
    version: str = Field(min_length=1)
    records: list[EvalRecord] = Field(min_length=1)


def export_eval_json_schema(path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(EvalBatch.model_json_schema(), indent=2), encoding="utf-8")
