"""Eval framework — ground-truth datasets + per-task scoring.

This module is the offline counterpart of the runtime. Where the
:class:`Agent` and :class:`TaskQueue` move tasks forward, the eval
framework runs a known set of (input, expected_output) tuples through
an agent and grades the result.

The grading strategy is intentionally simple:

1. **String-equality** for exact-match cases.
2. **Substring / keyword match** for "must contain X" cases.
3. **Custom callable** for callers who need something fancier (e.g.
   embedding cosine similarity, regex match, JSON-schema validation).

The framework does *not* claim to be a general-purpose eval harness —
the goal is to support regression testing for the specific agents we
ship, with results the team can read in a YAML report.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union

import yaml

from app.db import session_scope
from app.models import Run, RunStatus


class GradingStrategy(str, Enum):
    """How a single eval task is graded."""

    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"
    CUSTOM = "custom"


@dataclass
class EvalTask:
    """A single ground-truth case."""

    id: str
    input: dict[str, Any]
    expected_output: Any
    grading: GradingStrategy = GradingStrategy.EXACT
    pattern: Optional[str] = None  # for REGEX
    keywords: list[str] = field(default_factory=list)  # for CONTAINS
    custom_grader: Optional[Callable[[Any, Any], float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSet:
    """A named collection of :class:`EvalTask`."""

    id: str
    name: str
    tasks: list[EvalTask] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "EvalSet":
        """Load an eval set from a YAML file.

        Expected schema::

            id: my-eval-set
            name: Smoke test
            metadata:
              owner: agent-team
            tasks:
              - id: case-1
                input:
                  prompt: "What is 2+2?"
                expected_output: "4"
                grading: exact
              - id: case-2
                input:
                  prompt: "List 3 prime numbers"
                expected_output: "doesn't matter, must include 'prime'"
                grading: contains
                keywords: ["prime"]
        """
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        tasks: list[EvalTask] = []
        for raw in data.get("tasks", []):
            tasks.append(
                EvalTask(
                    id=raw["id"],
                    input=raw.get("input", {}),
                    expected_output=raw.get("expected_output"),
                    grading=GradingStrategy(raw.get("grading", "exact")),
                    pattern=raw.get("pattern"),
                    keywords=raw.get("keywords", []),
                    metadata=raw.get("metadata", {}),
                )
            )
        return cls(
            id=data.get("id", path.stem),
            name=data.get("name", path.stem),
            tasks=tasks,
            metadata=data.get("metadata", {}),
        )


@dataclass
class EvalTaskScore:
    """Per-task result."""

    task_id: str
    score: float
    passed: bool
    duration_s: float
    actual_output: Any = None
    error: Optional[str] = None


@dataclass
class EvalReport:
    """Aggregate result across all tasks in an :class:`EvalSet`."""

    eval_set_id: str
    agent_id: str
    started_at: float
    finished_at: float
    scores: list[EvalTaskScore] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.scores)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.scores if s.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total) if self.total else 0.0

    @property
    def average_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.score for s in self.scores) / len(self.scores)

    @property
    def duration_s(self) -> float:
        return self.finished_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_set_id": self.eval_set_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "scores": [
                {
                    "task_id": s.task_id,
                    "score": s.score,
                    "passed": s.passed,
                    "duration_s": s.duration_s,
                    "actual_output": s.actual_output,
                    "error": s.error,
                }
                for s in self.scores
            ],
            "metadata": self.metadata,
        }


class EvalFramework:
    """Run an eval set through an agent and produce an :class:`EvalReport`."""

    def __init__(self, eval_set_dir: Optional[Union[str, Path]] = None) -> None:
        self.eval_set_dir = (
            Path(eval_set_dir) if eval_set_dir else Path("./eval_sets")
        )

    def load_eval_set(self, eval_set_id: str) -> EvalSet:
        """Load a YAML eval set by id (filename)."""
        path = self.eval_set_dir / f"{eval_set_id}.yaml"
        if not path.exists():
            # Try direct path.
            path = Path(eval_set_id)
        return EvalSet.from_yaml(path)

    def grade(self, task: EvalTask, actual_output: Any) -> tuple[float, bool]:
        """Compute a (score, passed) tuple for one task."""
        try:
            if task.grading is GradingStrategy.EXACT:
                score = 1.0 if actual_output == task.expected_output else 0.0
                return score, score >= 1.0
            if task.grading is GradingStrategy.CONTAINS:
                text = str(actual_output)
                if not task.keywords:
                    return 0.0, False
                hits = sum(1 for kw in task.keywords if kw in text)
                score = hits / len(task.keywords)
                return score, score >= 1.0
            if task.grading is GradingStrategy.REGEX:
                import re
                text = str(actual_output)
                if not task.pattern:
                    return 0.0, False
                matched = re.search(task.pattern, text) is not None
                return (1.0 if matched else 0.0), matched
            if task.grading is GradingStrategy.CUSTOM:
                if task.custom_grader is None:
                    return 0.0, False
                score = float(task.custom_grader(actual_output, task.expected_output))
                return score, score >= 1.0
        except Exception:  # noqa: BLE001 — grader bugs must not crash the run
            return 0.0, False
        return 0.0, False

    async def run_eval(
        self,
        agent_id: uuid.UUID,
        eval_set_id: str,
        runner: Optional[Callable[[EvalTask], Any]] = None,
    ) -> EvalReport:
        """Run an eval set and return an :class:`EvalReport`.

        Parameters
        ----------
        agent_id : UUID
            The agent under test. Used as the report's agent_id field
            and (optionally) for writing a :class:`Run` audit row.
        eval_set_id : str
            Filename of the YAML eval set (without extension).
        runner : callable, optional
            ``runner(task) -> actual_output``. Defaults to a stub that
            returns the task's expected_output (useful for sanity tests
            of the grading path itself).
        """
        eval_set = self.load_eval_set(eval_set_id)
        report = EvalReport(
            eval_set_id=eval_set.id,
            agent_id=str(agent_id),
            started_at=time.time(),
            finished_at=0.0,
            metadata=eval_set.metadata,
        )
        effective_runner = runner or _default_runner
        for task in eval_set.tasks:
            started = time.time()
            try:
                if asyncio.iscoroutinefunction(effective_runner):
                    actual = await effective_runner(task)
                else:
                    actual = effective_runner(task)
                score, passed = self.grade(task, actual)
                report.scores.append(
                    EvalTaskScore(
                        task_id=task.id,
                        score=score,
                        passed=passed,
                        duration_s=time.time() - started,
                        actual_output=actual,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — capture per-task
                report.scores.append(
                    EvalTaskScore(
                        task_id=task.id,
                        score=0.0,
                        passed=False,
                        duration_s=time.time() - started,
                        error=repr(exc),
                    )
                )
        report.finished_at = time.time()

        # Best-effort: persist an audit Run row so the eval shows up in
        # the run list. Failure here must not change the report contents.
        try:
            await _persist_eval_run(agent_id, report)
        except Exception:  # noqa: BLE001
            pass

        return report


def _default_runner(task: EvalTask) -> Any:
    """Default runner used when the caller doesn't supply one.

    Returns the expected_output, which means every task passes. This is
    useful for testing the grading framework itself but should never
    be used for an actual eval — the caller should always inject a
    real :class:`Agent` runner.
    """
    return task.expected_output


async def _persist_eval_run(agent_id: uuid.UUID, report: EvalReport) -> None:
    """Write the eval result into the runs table."""
    import json as _json

    async with session_scope() as session:
        run = Run(
            agent_id=agent_id,
            started_at=_epoch_to_dt(report.started_at),
            finished_at=_epoch_to_dt(report.finished_at),
            status=(
                RunStatus.SUCCESS.value
                if report.failed == 0
                else RunStatus.PARTIAL.value
                if report.passed > 0
                else RunStatus.FAILED.value
            ),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error_message=None,
            log={
                "kind": "eval",
                "eval_set_id": report.eval_set_id,
                "pass_rate": report.pass_rate,
                "average_score": report.average_score,
                "scores": [
                    {
                        "task_id": s.task_id,
                        "score": s.score,
                        "passed": s.passed,
                    }
                    for s in report.scores
                ],
                "report_json": _json.dumps(report.to_dict(), default=str)[:60_000],
            },
        )
        session.add(run)


def _epoch_to_dt(epoch: float) -> Any:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc)