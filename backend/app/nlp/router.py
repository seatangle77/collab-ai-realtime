"""
NLP 微服务路由
- 前缀：/api/nlp
- 鉴权：X-Admin-Token（复用现有 require_admin）
- 接口：segment / embed / similarity / candidate_recall / has_reasoning / generate_summary / assess_gap
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
    tfidf,
)

router = APIRouter(prefix="/api/nlp", tags=["nlp"])

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


# ── 5. extract_keywords_broad ────────────────────────────────────────────────

class ExtractKeywordsBroadRequest(BaseModel):
    texts: list[str]
    top_n: int = Field(default=10, ge=1, le=50)


class ExtractKeywordsBroadResponse(BaseModel):
    keywords: list[str]


@router.post("/extract_keywords_broad", response_model=ExtractKeywordsBroadResponse)
def extract_keywords_broad(req: ExtractKeywordsBroadRequest, _: bool = Depends(require_admin)):
    keywords = tfidf.extract_tfidf_broad(req.texts, top_n=req.top_n)
    return {"keywords": keywords}


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


# ── 10. generate_group_silence（fast_model，实时沉默破冰）────────────────────

class GenerateGroupSilenceRequest(BaseModel):
    summary: str = ""
    transcripts: str = ""
    silence_s: int = 0


class GenerateGroupSilenceResponse(BaseModel):
    content: str


@router.post("/generate_group_silence", response_model=GenerateGroupSilenceResponse)
async def generate_group_silence_route(
    req: GenerateGroupSilenceRequest,
    _: bool = Depends(require_admin),
):
    content = await push_content.generate_group_silence(
        summary=req.summary,
        transcripts=req.transcripts,
        silence_s=req.silence_s,
    )
    return {"content": content}


# ── 11. analyze_members（heavy_model，2分钟全员分析）─────────────────────────

class MemberMetricsItem(BaseModel):
    user_id: str
    speaking_ratio: float = 0.0
    silence_s: float = 0.0
    ttr: float | None = None
    arg_density: float | None = None
    srep: float | None = None
    info_gain: float | None = None
    has_reasoning: bool | None = None
    has_evidence: bool | None = None


class AnalyzeMembersTranscriptItem(BaseModel):
    transcript_id: str
    user_id: str
    speaker_name: str = ""
    text: str


class AnalyzeMembersRequest(BaseModel):
    summary: str = ""
    transcripts: list[AnalyzeMembersTranscriptItem] = Field(default_factory=list)
    members: list[MemberMetricsItem] = Field(default_factory=list)


class MemberAnalysisItem(BaseModel):
    user_id: str
    challenge_type: str
    needs_prompt: bool
    analysis: str
    content: str
    anchor: dict[str, Any] | None = None


class AnalyzeMembersResponse(BaseModel):
    members: list[MemberAnalysisItem]


@router.post("/analyze_members", response_model=AnalyzeMembersResponse)
async def analyze_members_route(
    req: AnalyzeMembersRequest,
    _: bool = Depends(require_admin),
):
    transcripts_text = "\n".join(
        f"[{t.transcript_id}] {t.speaker_name or t.user_id}：{t.text}"
        for t in req.transcripts
    )
    members_metrics_text = "\n".join(
        f"- {m.user_id}：发言比例={round(m.speaking_ratio * 100, 1)}%"
        f" 静默={round(m.silence_s)}s TTR={m.ttr} 论证密度={m.arg_density}"
        f" Srep={m.srep} 信息增益={m.info_gain}"
        f" 有论证={m.has_reasoning} 有证据={m.has_evidence}"
        for m in req.members
    )
    result = await push_content.analyze_members_batch(
        summary=req.summary,
        transcripts_text=transcripts_text,
        members_metrics_text=members_metrics_text,
    )
    return result

