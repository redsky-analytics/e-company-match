"""Main orchestration: preprocessing, candidate gen, scoring, decision."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from cm.config import MatchConfig
from cm.embeddings import EmbeddingIndex, EmbeddingProvider
from cm.index import BlockingIndex
from cm.llm_arbiter import LLMArbiter, LLMProvider
from cm.normalize import normalize
from cm.scoring import score_pair
from cm.types import MatchResult, NormalizedName, ScoredCandidate

log = structlog.get_logger()


@dataclass
class MatcherStats:
    """Statistics collected during matching."""

    a_count: int = 0
    b_count: int = 0
    comparisons: int = 0
    no_candidates: int = 0
    llm_calls: int = 0
    llm_overrides: int = 0
    embedding_api_calls: int = 0
    embedding_cache_hits: int = 0
    decisions: dict[str, int] = field(default_factory=lambda: {
        "MATCH": 0, "NO_MATCH": 0, "REVIEW": 0
    })


class Matcher:
    """Company name matcher orchestrating the full pipeline."""

    def __init__(
        self,
        config: MatchConfig | None = None,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.config = config or MatchConfig()
        self.index = BlockingIndex(self.config.candidates)
        self.embedding_index = EmbeddingIndex(
            self.config.embedding, embedding_provider
        )
        self.arbiter = LLMArbiter(self.config.llm, llm_provider)
        self._b_names: list[NormalizedName] = []
        self.stats = MatcherStats()

    def preprocess_b(self, names: list[str]) -> None:
        """Stage 0: Normalize all B names and build indices."""
        self.stats.b_count = len(names)
        log.info("normalize_b_start", count=len(names))
        self._b_names = [normalize(n, self.config) for n in names]
        log.info("normalize_b_done")

        log.info("build_blocking_index_start")
        self.index.build(self._b_names)
        log.info("build_blocking_index_done")

        if self.config.embedding.enabled:
            log.info("build_embedding_index_start")
            core_strings = [n.core_string for n in self._b_names]
            self.embedding_index.build(core_strings)
            log.info("build_embedding_index_done")

    def match_one(self, a_name: str, a_id: int = 0) -> MatchResult:
        """Match a single A name against the B index."""
        a = normalize(a_name, self.config)
        log.debug(
            "match_one_start",
            a_id=a_id,
            a_name=a.original,
            core_string=a.core_string,
            acronym=a.acronym,
        )

        # Stage 1: Candidate generation
        embedding_candidates: list[int] | None = None
        if self.config.embedding.enabled:
            b_ids, sims = self.embedding_index.query(a.core_string)
            embedding_candidates = b_ids
            log.debug(
                "embedding_candidates",
                count=len(b_ids),
                top_3=[(bid, round(s, 3)) for bid, s in zip(b_ids[:3], sims[:3])],
            )

        candidates = self.index.retrieve_candidates(a, embedding_candidates)
        log.debug("candidates_retrieved", count=len(candidates))

        if not candidates:
            log.debug("no_candidates", a_name=a.original)
            self.stats.no_candidates += 1
            self.stats.decisions["NO_MATCH"] += 1
            return MatchResult(
                a_id=a_id,
                a_name=a.original,
                b_id=None,
                b_name=None,
                decision="NO_MATCH",
                score=0.0,
                reasons=["no_candidates"],
            )

        # Stage 2: Score all candidates
        scored_candidates: list[ScoredCandidate] = []
        for cand in candidates:
            b = self._b_names[cand.b_id]

            # Get embedding cosine if available
            embedding_cosine: float | None = None
            if self.config.embedding.enabled:
                embedding_cosine = self.embedding_index.cosine_similarity(
                    a.core_string, b.core_string
                )

            sc = score_pair(a, b, self.config, embedding_cosine)
            sc.b_id = cand.b_id
            scored_candidates.append(sc)

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x.score, reverse=True)
        self.stats.comparisons += len(scored_candidates)

        best = scored_candidates[0]
        runner_up_score = scored_candidates[1].score if len(scored_candidates) > 1 else None
        margin = (best.score - runner_up_score) if runner_up_score is not None else None

        best_b = self._b_names[best.b_id]

        log.debug(
            "scoring_done",
            best_b_name=best_b.original,
            best_score=round(best.score, 4),
            runner_up_score=round(runner_up_score, 4) if runner_up_score else None,
            margin=round(margin, 4) if margin else None,
            reasons=best.reasons,
        )

        # Stage 3: Decision bands
        decision = self._decide(best.score, runner_up_score, margin)
        log.debug("decision_band", decision=decision)

        used_llm = False

        # Stage 4: Optional LLM arbitration for AMBIGUOUS
        if decision == "REVIEW" and self.config.llm.enabled:
            log.debug("llm_arbitration_check", a_name=a.original)
            # Check top-K candidates for LLM eligibility
            top_k = scored_candidates[: self.config.llm.top_k]
            for sc in top_k:
                b_cand = self._b_names[sc.b_id]
                sc_runner = top_k[1].score if len(top_k) > 1 else None
                if self.arbiter.is_eligible(a, b_cand, sc, sc_runner):
                    log.info(
                        "llm_arbitration_call",
                        a_name=a.original,
                        b_name=b_cand.original,
                        score=round(sc.score, 4),
                    )
                    llm_decision, llm_response = self.arbiter.arbitrate(
                        a, b_cand, sc, sc_runner,
                        strip_categories=self.config.normalization.strip_categories,
                    )
                    log.info(
                        "llm_arbitration_result",
                        llm_decision=llm_response.decision,
                        confidence=llm_response.confidence,
                        reason=llm_response.reason,
                        final_decision=llm_decision,
                    )
                    if llm_decision != "REVIEW":
                        decision = llm_decision
                        best = sc
                        best_b = b_cand
                        used_llm = True
                        self.stats.llm_overrides += 1
                        break

        # Track final decision
        self.stats.decisions[decision] += 1

        log.debug(
            "match_one_done",
            a_name=a.original,
            decision=decision,
            matched_b=best_b.original if decision == "MATCH" else None,
            score=round(best.score, 4),
            used_llm=used_llm,
        )

        return MatchResult(
            a_id=a_id,
            a_name=a.original,
            b_id=best.b_id if decision == "MATCH" else None,
            b_name=best_b.original if decision == "MATCH" else None,
            decision=decision,
            score=best.score,
            runner_up_score=runner_up_score,
            margin=margin,
            used_llm=used_llm,
            reasons=best.reasons,
            debug={
                "top_candidates": [
                    {"b_id": sc.b_id, "score": sc.score, "reasons": sc.reasons}
                    for sc in scored_candidates[:5]
                ],
                "warnings": a.meta.get("warnings", []),
                "candidate_count": len(candidates),
            },
        )

    def match_all(self, a_names: list[str]) -> list[MatchResult]:
        """Match all A names against the B index."""
        self.stats.a_count = len(a_names)

        # Pre-compute embeddings for all A names in one batch
        if self.config.embedding.enabled:
            log.info("precompute_a_embeddings_start", count=len(a_names))
            a_normalized = [normalize(n, self.config) for n in a_names]
            a_core_strings = [n.core_string for n in a_normalized]
            self.embedding_index.precompute(a_core_strings)
            log.info("precompute_a_embeddings_done")

        results: list[MatchResult] = []
        for i, name in enumerate(a_names):
            result = self.match_one(name, a_id=i)
            results.append(result)
            if (i + 1) % 1000 == 0:
                log.info(
                    "match_progress",
                    processed=i + 1,
                    total=len(a_names),
                    llm_calls=self.arbiter.calls_made,
                )

        # Collect final stats
        self.stats.llm_calls = self.arbiter.calls_made
        self.stats.embedding_api_calls = self.embedding_index.api_calls
        self.stats.embedding_cache_hits = self.embedding_index.cache_hits

        return results

    def _decide(
        self, best_score: float, runner_up_score: float | None, margin: float | None
    ) -> str:
        """Apply decision band rules."""
        t = self.config.thresholds

        if best_score <= t.t_low:
            return "NO_MATCH"

        if best_score >= t.t_high:
            if margin is None or margin >= t.margin:
                return "MATCH"

        return "REVIEW"
