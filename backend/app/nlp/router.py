"""
NLP 微服务路由
- 前缀：/api/nlp
- 鉴权：X-Admin-Token（复用现有 require_admin）
- 接口：segment / embed / similarity / tfidf / candidate_recall / has_reasoning / generate_push / generate_push_batch / assess_gap / generate_summary
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..admin.deps import require_admin
from . import (
    embedder,
    similarity,
    segmenter,
    reasoning,
    push_content,
    summary,
    candidate_recall,
    structured_push_content,
)

router = APIRouter(prefix="/api/nlp", tags=["nlp"])

BatchChallengeType = Literal[
    "personal_stagnation",
    "group_stagnation",
    "shallow_expression",
    "information_gap",
    "none",
]


# ── 1. segment ────────────────────────────────────────────────────────────────

class SegmentRequest(BaseModel):
    text: str


class SegmentResponse(BaseModel):
    tokens: list[str]
    token_count: int
    unique_count: int
    ttr: float
    arg_density: float


@router.post("/segment", response_model=SegmentResponse)
def segment(req: SegmentRequest, _: bool = Depends(require_admin)):
    return segmenter.segment(req.text)


# ── 2. embed ─────────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


@router.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest, _: bool = Depends(require_admin)):
    return {"embeddings": embedder.encode(req.texts)}


# ── 3. similarity ─────────────────────────────────────────────────────────────

class SimilarityPair(BaseModel):
    vec_a: list[float]
    vec_b: list[float]


class SimilarityRequest(BaseModel):
    pairs: list[SimilarityPair]


class SimilarityResponse(BaseModel):
    scores: list[float]


@router.post("/similarity", response_model=SimilarityResponse)
def compute_similarity(req: SimilarityRequest, _: bool = Depends(require_admin)):
    pairs = [{"vec_a": p.vec_a, "vec_b": p.vec_b} for p in req.pairs]
    return {"scores": similarity.batch_similarity(pairs)}


# ── 4. keyword_recall_with_gap ────────────────────────────────────────────────

class KeywordRecallItem(BaseModel):
    word: str
    needs_prompt: bool
    target_user_id: str
    reason: str


class KeywordRecallWithGapRequest(BaseModel):
    member_texts: dict[str, str]


class KeywordRecallWithGapResponse(BaseModel):
    keywords: list[KeywordRecallItem]


@router.post("/keyword_recall_with_gap", response_model=KeywordRecallWithGapResponse)
def keyword_recall_with_gap(req: KeywordRecallWithGapRequest, _: bool = Depends(require_admin)):
    return candidate_recall.recall_with_gap(req.member_texts)


# ── 6. has_reasoning ─────────────────────────────────────────────────────────

class ReasoningRequest(BaseModel):
    text: str


class ReasoningResponse(BaseModel):
    has_reasoning: bool
    has_evidence: bool
    method: str                           # "rule" 或 "llm"


@router.post("/has_reasoning", response_model=ReasoningResponse)
def check_reasoning(req: ReasoningRequest, _: bool = Depends(require_admin)):
    return reasoning.has_reasoning(req.text)


# ── 7. generate_push ──────────────────────────────────────────────────────────

class GeneratePushRequest(BaseModel):
    trigger_type: str                          # group_silence / low_participation / shallow_discussion / info_gap
    summary: str = ""
    transcripts: str = ""                      # 调用方格式化好的发言文本
    username: str = ""
    silence_s: int = 0
    speaking_ratio: float = 0.0
    triggered_metrics: str = ""
    keyword: str = ""
    skw_score: float = 0.0


class GeneratePushResponse(BaseModel):
    content: str


@router.post("/generate_push", response_model=GeneratePushResponse)
def generate_push(req: GeneratePushRequest, _: bool = Depends(require_admin)):
    content = push_content.generate_push_content(
        trigger_type=req.trigger_type,
        summary=req.summary,
        transcripts=req.transcripts,
        username=req.username,
        silence_s=req.silence_s,
        speaking_ratio=req.speaking_ratio,
        triggered_metrics=req.triggered_metrics,
        keyword=req.keyword,
        skw_score=req.skw_score,
    )
    return {"content": content}


# ── 8. generate_push_batch ────────────────────────────────────────────────────

class BatchMemberInput(BaseModel):
    user_id: str


class BatchTargetInput(BaseModel):
    user_id: str
    challenge_type: BatchChallengeType
    evidence: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str
    design_goal: str


class GeneratePushBatchRequest(BaseModel):
    session_id: str
    summary: str = ""
    transcripts: str = ""
    members: list[BatchMemberInput] = Field(default_factory=list)
    targets: list[BatchTargetInput] = Field(default_factory=list)


class BatchAnalysisItem(BaseModel):
    user_id: str
    challenge_type: BatchChallengeType
    needs_prompt: bool
    analysis: str
    content: str


class GeneratePushBatchResponse(BaseModel):
    items: list[BatchAnalysisItem]


@router.post("/generate_push_batch", response_model=GeneratePushBatchResponse)
def generate_push_batch(req: GeneratePushBatchRequest, _: bool = Depends(require_admin)):
    items = push_content.generate_push_content_batch(
        session_id=req.session_id,
        summary=req.summary,
        transcripts=req.transcripts,
        members=[m.model_dump() for m in req.members],
        targets=[t.model_dump() for t in req.targets],
    )
    return {"items": items}


# ── 9. generate_summary ──────────────────────────────────────────────────────

class TranscriptItem(BaseModel):
    user_id: str
    text: str


class GenerateSummaryRequest(BaseModel):
    transcripts: list[TranscriptItem]
    prev_summary: str = ""


class GenerateSummaryResponse(BaseModel):
    summary: str


@router.post("/generate_summary", response_model=GenerateSummaryResponse)
def generate_summary_route(req: GenerateSummaryRequest, _: bool = Depends(require_admin)):
    result = summary.generate_summary(
        transcripts=[t.model_dump() for t in req.transcripts],
        prev_summary=req.prev_summary,
    )
    return {"summary": result}


# ── 11. generate_push_structured ─────────────────────────────────────────────

StructuredPushTriggerType = Literal["low_participation", "shallow_discussion", "group_silence"]


class StructuredTranscriptItem(BaseModel):
    transcript_id: str
    user_id: str
    speaker_name: str | None = None
    text: str


class StructuredCandidatePoint(BaseModel):
    transcript_id: str
    speaker_id: str
    text: str


class GenerateStructuredPushRequest(BaseModel):
    trigger_type: StructuredPushTriggerType
    summary: str = ""
    transcripts: list[StructuredTranscriptItem] = Field(default_factory=list)
    user_id: str
    trigger_metrics: dict[str, Any] = Field(default_factory=dict)
    candidate_points: list[StructuredCandidatePoint] = Field(default_factory=list)


class StructuredAnchorOut(BaseModel):
    transcript_id: str
    speaker_id: str
    text: str


class GenerateStructuredPushResponse(BaseModel):
    needs_prompt: bool
    anchor: StructuredAnchorOut | None = None
    content: str


@router.post("/generate_push_structured", response_model=GenerateStructuredPushResponse)
def generate_push_structured(req: GenerateStructuredPushRequest, _: bool = Depends(require_admin)):
    result = structured_push_content.generate_structured_push_content(
        trigger_type=req.trigger_type,
        summary=req.summary,
        transcripts=[t.model_dump() for t in req.transcripts],
        user_id=req.user_id,
        trigger_metrics=req.trigger_metrics,
        candidate_points=[p.model_dump() for p in req.candidate_points],
    )
    return result
