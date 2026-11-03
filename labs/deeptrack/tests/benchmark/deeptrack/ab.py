"""tests/benchmark/deeptrack/ab: the ontology A/B — pre-registered in BENCH.md; run with `make bench`.

Every sample is one fresh thread of one case on one arm, judged by the case's single correct outcome. Arms rotate
per (repeat, case) so drift cancels; one warm-up turn per arm is discarded. Each sample is appended to the JSONL as
it lands: a run that dies resumes from what it wrote (`--resume`), never relaunched whole. The summary decides H1 by
the case-clustered bootstrap interval of the mean difference against the pre-registered threshold — nothing else."""

import importlib.metadata
import json
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
from cyclopts import App
from rich.console import Console

from deeptrack.lifespan import engines, services
from deeptrack.lifespan.sealed import lifespan
from deeptrack.models.arm import Arm
from deeptrack.services.chat import ChatService
from infra.settings import settings as st
from processors.models import EventKind, EventPhase, RunEvent

HERE: Final[Path] = Path(__file__).parent
REPORTS: Final[Path] = HERE.parents[2] / "reports"
THRESHOLD: Final[float] = 0.20
RESAMPLES: Final[int] = 10_000
WARMUP: Final[str] = "¿Qué coberturas tiene la póliza pol-2002?"
PROPOSING: Final[frozenset[str]] = frozenset({"proponer_denuncia", "proponer_endoso"})
CONSOLE: Final[Console] = Console(highlight=False)
VERSIONS: Final[tuple[str, ...]] = ("deepagents", "langgraph", "langchain-google-genai", "langfuse")


@dataclass(frozen=True, slots=True)
class Case:
    """One transaction with one correct outcome: `valid` stops for approval with `expect`, `invalid` never does."""

    id: str
    kind: str
    message: str
    expect: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Sample:
    """One case on one arm in one repeat, judged; `correct` is None when the run failed for a reason outside the arm."""

    arm: str
    case: str
    kind: str
    repeat: int
    correct: bool | None
    stopped_by: str
    blocked: str | None
    latency_ms: float
    tokens_in: int
    tokens_out: int
    llm_calls: int
    mcp_calls: int
    error: str = ""
    trace_id: str = ""
    proposal: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.arm, self.case, self.repeat)


class AbBench:
    """The schedule, the judging of one sample, and the summary."""

    __slots__ = ("_cases", "_out", "_repeats")

    def __init__(self, cases: tuple[Case, ...], repeats: int, out: Path) -> None:
        self._cases = cases
        self._repeats = repeats
        self._out = out

    @staticmethod
    def _run_order(repeat: int, index: int) -> tuple[Arm, ...]:
        """The three arms rotated by (repeat + case index): every arm runs first, second and third equally often."""
        arms = tuple(Arm)
        shift = (repeat + index) % len(arms)
        return arms[shift:] + arms[:shift]

    @staticmethod
    def _run_judge(
        case: Case, frames: list[RunEvent], interrupt: dict[str, Any] | None, blocked: str | None
    ) -> tuple[bool, str]:
        """The case's verdict and who stopped an invalid one: `nobody` (it reached approval), `gate`, or `agent`."""
        proposed = any(f.name in PROPOSING and f.phase is EventPhase.START for f in frames)
        stopper = "nobody" if interrupt is not None else "guard" if blocked else "gate" if proposed else "agent"
        match case.kind:
            case "valid":
                return interrupt is not None and interrupt.get("propuesta") == case.expect, stopper
            case _:
                return interrupt is None, stopper

    async def _run_sample(self, chat: ChatService, arm: Arm, case: Case, repeat: int) -> Sample:
        frames: list[RunEvent] = []
        began = time.perf_counter()
        try:
            turn = await chat.turn(f"ab-{arm}-{case.id}-{repeat}-{time.time_ns()}", case.message, frames.append)
        except Exception as error:  # noqa: BLE001 — an infrastructure failure is recorded, not judged against the arm
            return self._run_measure(
                frames, arm, case, repeat, began, None, "error", None, f"{type(error).__name__}: {error}"
            )
        correct, stopper = self._run_judge(case, frames, turn.interrupt, turn.blocked)
        measured = self._run_measure(frames, arm, case, repeat, began, correct, stopper, turn.blocked)
        ### what reached approval, and where its trace is: a wrong outcome is diagnosed from the sample alone.
        return replace(measured, trace_id=turn.trace_id, proposal=(turn.interrupt or {}).get("propuesta"))

    @staticmethod
    def _run_measure(  # noqa: PLR0917 — one sample's every field, positional at its two call sites
        frames: list[RunEvent],
        arm: Arm,
        case: Case,
        repeat: int,
        began: float,
        correct: bool | None,
        stopper: str,
        blocked: str | None,
        error: str = "",
    ) -> Sample:
        ends = [f for f in frames if f.kind is EventKind.LLM and f.phase is EventPhase.END]
        return Sample(
            arm=str(arm),
            case=case.id,
            kind=case.kind,
            repeat=repeat,
            correct=correct,
            stopped_by=stopper,
            blocked=blocked,
            latency_ms=round((time.perf_counter() - began) * 1000, 1),
            tokens_in=sum(int(f.payload.get("usage", {}).get("input_tokens", 0)) for f in ends),
            tokens_out=sum(int(f.payload.get("usage", {}).get("output_tokens", 0)) for f in ends),
            llm_calls=sum(1 for f in frames if f.kind is EventKind.LLM and f.phase is EventPhase.START),
            mcp_calls=sum(1 for f in frames if f.kind is EventKind.MCP and f.phase is EventPhase.START),
            error=error,
        )

    def _run_append(self, sample: Sample) -> Sample:
        with self._out.open("a") as sink:
            sink.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
        CONSOLE.print(
            f"{sample.arm:14s} {sample.case:18s} r{sample.repeat} correct={sample.correct} by={sample.stopped_by} {sample.latency_ms:.0f}ms"
        )
        return sample

    ############################################################

    def done(self) -> dict[tuple[str, str, int], Sample]:
        """Samples already written: a resumed run skips them."""
        lines = self._out.read_text().splitlines() if self._out.exists() else []
        samples = [Sample(**json.loads(line)) for line in lines if line.strip()]
        return {sample.key: sample for sample in samples}

    async def run(self) -> list[Sample]:
        """Warm up, then every (repeat, case, arm) in rotated order, appended as it lands."""
        written = self.done()
        async with lifespan() as state:
            mounted = state.providers
            chats = {arm: services.chat(mounted, engines.built(mounted, arm), arm) for arm in Arm}
            [await chats[arm].turn(f"warmup-{arm}-{time.time_ns()}", WARMUP, lambda _: None) for arm in Arm]
            schedule = [
                (repeat, case, arm)
                for repeat in range(self._repeats)
                for index, case in enumerate(self._cases)
                for arm in self._run_order(repeat, index)
                if (str(arm), case.id, repeat) not in written
            ]
            fresh = [
                self._run_append(await self._run_sample(chats[arm], arm, case, repeat))
                for repeat, case, arm in schedule
            ]
        return [*written.values(), *fresh]


class AbSummary:
    """The pre-registered decision and every recorded number, as Markdown."""

    __slots__ = ("_samples",)

    def __init__(self, samples: list[Sample]) -> None:
        self._samples = [each for each in samples if each.correct is not None]

    def _clusters(self, a: str, b: str) -> np.ndarray:
        """Per-case mean difference a - b of correctness over the repeats both arms judged: one value per case.

        Outcomes repeat almost exactly within a case, so the case is the independent unit (BENCH.md, revision 2)."""
        by = {(s.arm, s.case, s.repeat): float(bool(s.correct)) for s in self._samples}
        cases = sorted({case for arm, case, _ in by if arm == a})
        diffs = [
            [
                by[(a, case, repeat)] - by[(b, case, repeat)]
                for arm, c, repeat in by
                if arm == a and c == case and (b, case, repeat) in by
            ]
            for case in cases
        ]
        return np.array([float(np.mean(each)) for each in diffs if each])

    @staticmethod
    def _interval(diffs: np.ndarray) -> tuple[float, float, float]:
        """Mean difference and its 95 % percentile bootstrap interval, resampling the clusters (cases)."""
        rng = np.random.default_rng(7)
        means = rng.choice(diffs, size=(RESAMPLES, diffs.size), replace=True).mean(axis=1)
        return float(diffs.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

    @staticmethod
    def _verdict(low: float, high: float) -> str:
        match (low > THRESHOLD, high < THRESHOLD):
            case (True, _):
                return f"**worth it** — the whole interval is above +{THRESHOLD:.2f}"
            case (_, True):
                return f"**not worth it at this threshold** — the whole interval is below +{THRESHOLD:.2f}"
            case _:
                return f"**undecided at this n** — the interval crosses +{THRESHOLD:.2f}"

    def _arm_accuracy(self, arm: Arm, kind: str) -> float:
        judged = [float(bool(s.correct)) for s in self._samples if s.arm == arm and kind in ("all", s.kind)]
        return float(np.mean(judged)) if judged else float("nan")

    def _arm_row(self, arm: Arm) -> str:
        mine = [s for s in self._samples if s.arm == arm]
        latency = np.array([s.latency_ms for s in mine] or [0.0])
        mean = lambda values: float(np.mean(values)) if values else 0.0  # noqa: E731 — a one-line local reducer
        return (
            f"| `{arm}` | {len(mine)} | {self._arm_accuracy(arm, 'all'):.2f} | {self._arm_accuracy(arm, 'valid'):.2f} "
            f"| {self._arm_accuracy(arm, 'invalid'):.2f} | {np.percentile(latency, 50):.0f} | {np.percentile(latency, 95):.0f} "
            f"| {mean([s.tokens_in for s in mine]):.0f} | {mean([s.tokens_out for s in mine]):.0f} "
            f"| {mean([s.llm_calls for s in mine]):.1f} | {mean([s.mcp_calls for s in mine]):.1f} |"
        )

    def _stopper_rows(self) -> list[str]:
        invalid = [s for s in self._samples if s.kind == "invalid"]
        names = ("gate", "agent", "guard", "nobody")
        return [
            f"| `{arm}` | "
            + " | ".join(str(sum(1 for s in invalid if s.arm == arm and s.stopped_by == n)) for n in names)
            + " |"
            for arm in Arm
        ]

    ############################################################

    def markdown(self, raw: Path, failed: int) -> str:
        """The report: decision first, then everything recorded."""
        h1 = self._clusters(Arm.FULL, Arm.NO_ONTOLOGY)
        h2 = self._clusters(Arm.FULL, Arm.NO_ONTOLOGIST)
        (m1, l1, u1), (m2, l2, u2) = self._interval(h1), self._interval(h2)
        versions = ", ".join(f"{name} {importlib.metadata.version(name)}" for name in VERSIONS)
        lines = [
            f"# Ontology A/B — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
            "",
            f"Pre-registration: `BENCH.md`. Raw samples: `{raw.name}`. Excluded (infrastructure failures): {failed}.",
            f"Chat {st.providers.drivers.chat.gemini.ref} · guard {st.providers.drivers.classify.gemini.ref} · {versions}.",
            "",
            "## Decision (H1: full - no_ontology > +0.20)",
            "",
            f"Mean difference **{m1:+.2f}**, 95 % case-clustered interval [{l1:+.2f}, {u1:+.2f}] over {h1.size} cases → {self._verdict(l1, u1)}.",
            "",
            f"Secondary, not decided on — full - no_ontologist: {m2:+.2f} [{l2:+.2f}, {u2:+.2f}] over {h2.size} cases.",
            "",
            "## Arms",
            "",
            "| Arm | n | correct | valid | invalid | p50 ms | p95 ms | tokens in | tokens out | LLM calls | MCP calls |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
            *(self._arm_row(arm) for arm in Arm),
            "",
            "## Who stopped the invalid cases (samples)",
            "",
            "| Arm | gate | agent | guard | nobody (reached approval) |",
            "|---|---|---|---|---|",
            *self._stopper_rows(),
            "",
        ]
        return "\n".join(lines)


app = App(name="ab", help="The ontology A/B bench (BENCH.md).")


@app.default
async def bench(repeats: int = 2, resume: Path | None = None) -> None:
    """Run the bench; `--resume reports/ab-….jsonl` continues a run that died."""
    REPORTS.mkdir(exist_ok=True)
    raw = resume or REPORTS / f"ab-{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl"
    cases = tuple(Case(**each) for each in json.loads((HERE / "cases.json").read_text()))
    samples = await AbBench(cases, repeats, raw).run()
    failed = sum(1 for each in samples if each.correct is None)
    summary = raw.with_suffix(".md")
    summary.write_text(AbSummary(samples).markdown(raw, failed))
    CONSOLE.print(summary.read_text())


app() if __name__ == "__main__" else None
