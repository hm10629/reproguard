"""Human review decisions for AI- and rule-generated passport records."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from .passport import ReproductionPack, REVIEW_DECISIONS, Review


class ReviewInputError(ValueError):
    """Raised when a human review submission is incomplete."""


def apply_review_decision(
    pack: ReproductionPack,
    *,
    review_id: str,
    decision: str,
    reviewer: str,
    note: str = "",
) -> Review:
    """Record one attributable decision and update compatible target states."""

    if decision not in REVIEW_DECISIONS - {"pending"}:
        raise ReviewInputError(f"不支持的人工复核决定：{decision}")
    if not reviewer.strip():
        raise ReviewInputError("复核人不能为空")
    if decision in {"rejected", "revised"} and not note.strip():
        raise ReviewInputError("驳回或修订时必须填写说明")

    original = pack
    pack = deepcopy(pack)
    review = next((item for item in pack.reviews if item.review_id == review_id), None)
    if review is None:
        raise ReviewInputError(f"找不到复核任务：{review_id}")
    if review.decision != "pending":
        raise ReviewInputError(f"复核任务 {review_id} 已经处理，不能重复提交")

    review.decision = decision
    review.reviewer = reviewer.strip()
    review.note = note.strip() or review.note
    review.reviewed_at = datetime.now(timezone.utc).isoformat()

    claim = next((item for item in pack.claims if item.claim_id == review.target_id), None)
    result = next((item for item in pack.results if item.result_id == review.target_id), None)
    evidence = next(
        (item for item in pack.evidence if item.evidence_id == review.target_id), None
    )
    deviation = next(
        (item for item in pack.deviations if item.deviation_id == review.target_id), None
    )

    if decision == "accepted":
        if claim is not None:
            claim.status = "confirmed"
        if result is not None:
            result.status = "confirmed"
        if evidence is not None:
            evidence.status = "confirmed"
            evidence.verification_level = "human_confirmed"
        if deviation is not None:
            deviation.status = "accepted"
            deviation.requires_review = False
            if note.strip():
                deviation.explanation = note.strip()
    elif decision == "revised":
        if claim is not None:
            claim.status = "partial"
        if result is not None:
            result.status = "partial"
        if deviation is not None:
            deviation.status = "explained"
            deviation.requires_review = False
            deviation.explanation = note.strip()
    elif decision == "rejected" and deviation is not None:
        deviation.status = "explained"
        deviation.requires_review = False
        deviation.explanation = f"人工判定该偏差不成立：{note.strip()}"

    pack.updated_at = review.reviewed_at
    pack.validate()
    original.__dict__.update(pack.__dict__)
    return next(item for item in original.reviews if item.review_id == review_id)
