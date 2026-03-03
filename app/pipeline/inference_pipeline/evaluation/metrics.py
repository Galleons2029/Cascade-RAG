from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Protocol, Sequence


@dataclass
class ScoreResult:
    name: str
    value: float
    reason: str = ""


class EvaluationMetric(Protocol):
    name: str

    def score(
        self,
        *,
        instruction: str,
        output: str,
        reference: str,
        context: str | None = None,
    ) -> ScoreResult: ...


def _normalize_text(value: str | None) -> str:
    return value or ""


def _split_sentences(text: str) -> list[str]:
    return [sentence.strip().lower() for sentence in re.split(r"[.!?]+", text) if sentence.strip()]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


class LevenshteinRatioMetric:
    name = "levenshtein_ratio"

    def score(
        self,
        *,
        instruction: str,
        output: str,
        reference: str,
        context: str | None = None,
    ) -> ScoreResult:
        answer_text = _normalize_text(output)
        reference_text = _normalize_text(reference)

        ratio = SequenceMatcher(
            None,
            answer_text,
            reference_text,
        ).ratio()

        return ScoreResult(
            name=self.name,
            value=ratio,
            reason=f"SequenceMatcher ratio between answer and reference: {ratio:.3f}",
        )


class HallucinationMetric:
    name = "hallucination"

    def score(
        self,
        *,
        instruction: str,
        output: str,
        reference: str,
        context: str | None = None,
    ) -> ScoreResult:
        sentences = _split_sentences(_normalize_text(output))
        reference_text = _normalize_text(reference).lower()

        if not sentences or not reference_text:
            return ScoreResult(
                name=self.name,
                value=0.0,
                reason="No sentences or reference text available for comparison.",
            )

        grounded = [sentence for sentence in sentences if sentence and sentence in reference_text]
        value = len(grounded) / len(sentences)
        reason = f"{len(grounded)}/{len(sentences)} answer sentences overlap with reference."

        return ScoreResult(name=self.name, value=value, reason=reason)


class ModerationMetric:
    name = "moderation"

    def __init__(self, blocked_keywords: Sequence[str] | None = None) -> None:
        default_keywords = {
            "violent",
            "hate",
            "terrorism",
            "extremist",
            "abuse",
            "weapon",
            "explosive",
        }
        self.blocked_keywords = set(blocked_keywords or default_keywords)

    def score(
        self,
        *,
        instruction: str,
        output: str,
        reference: str,
        context: str | None = None,
    ) -> ScoreResult:
        tokens = set(_tokenize(_normalize_text(output)))
        flagged = sorted(tokens & self.blocked_keywords)

        if flagged:
            return ScoreResult(
                name=self.name,
                value=0.0,
                reason=f"Flagged keywords detected: {', '.join(flagged)}",
            )

        return ScoreResult(
            name=self.name,
            value=1.0,
            reason="No blocked keywords detected.",
        )


__all__ = [
    "EvaluationMetric",
    "HallucinationMetric",
    "LevenshteinRatioMetric",
    "ModerationMetric",
    "ScoreResult",
]
