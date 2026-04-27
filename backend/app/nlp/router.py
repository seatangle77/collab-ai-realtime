"""
NLP 微服务路由
- 前缀：/api/nlp
- 鉴权：X-Admin-Token（复用现有 require_admin）
- 接口：segment / embed / similarity / candidate_recall / reasoning_batch / generate_summary / assess_gap
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
from .reasoning import batch_has_reasoning, MemberReasoningInput

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


# ── 6. reasoning_batch（全员批量，主分析链路用）──────────────────────────────

class BatchReasoningMemberInput(BaseModel):
    user_id: str
    text: str


class BatchReasoningRequest(BaseModel):
    members: list[BatchReasoningMemberInput]


class MemberReasoningResultOut(BaseModel):
    user_id: str
    reasoning_status: bool | None
    evidence_status: bool | None
    reasoning_source: str
    evidence_source: str


class BatchReasoningResponse(BaseModel):
    members: list[MemberReasoningResultOut]


@router.post("/reasoning_batch", response_model=BatchReasoningResponse)
def reasoning_batch(req: BatchReasoningRequest, _: bool = Depends(require_admin)):
    inputs: list[MemberReasoningInput] = [
        {"user_id": m.user_id, "text": m.text} for m in req.members
    ]
    results = batch_has_reasoning(inputs)
    return {"members": results}


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
    reasoning_status: bool | None = None
    evidence_status: bool | None = None
    reasoning_source: str | None = None
    evidence_source: str | None = None


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


def _format_metric(value: float | None, level_fn) -> str:
    if value is None:
        return "数据不足"
    return f"{round(value, 3)}（{level_fn(value)}）"


def _speaking_ratio_level(value: float) -> str:
    if value < 0.15:
        return "极低"
    if value < 0.25:
        return "偏低"
    return "正常"


def _silence_level(value: float) -> str:
    return "较长时间未发言" if value > 90 else "正常"


def _info_gain_level(value: float) -> str:
    return "低" if value < 0.3 else "正常或较高"


def _ttr_level(value: float) -> str:
    if value < 0.3:
        return "低"
    if value < 0.6:
        return "中"
    return "高"


def _arg_density_level(value: float) -> str:
    if value < 0.1:
        return "低"
    if value < 0.3:
        return "中"
    return "高"


def _srep_level(value: float) -> str:
    return "高/重复" if value > 0.65 else "正常"


def _format_status(value: bool | None) -> str:
    if value is None:
        return "数据不足"
    return "有" if value else "无"


@router.post("/analyze_members", response_model=AnalyzeMembersResponse)
async def analyze_members_route(
    req: AnalyzeMembersRequest,
    _: bool = Depends(require_admin),
):
    transcripts_text = "\n".join(
        f"[{t.transcript_id}] user_id={t.user_id} speaker_name={t.speaker_name or '未知'}：{t.text}"
        for t in req.transcripts
    )
    members_metrics_text = "\n".join(
        f"- {m.user_id}：\n"
        f"  发言比例 speaking_ratio = {round(m.speaking_ratio, 3)}（{_speaking_ratio_level(m.speaking_ratio)}）\n"
        f"  静默时长 silence_s = {round(m.silence_s)}s（{_silence_level(m.silence_s)}）\n"
        f"  信息增益 info_gain = {_format_metric(m.info_gain, _info_gain_level)}\n"
        f"  TTR = {_format_metric(m.ttr, _ttr_level)}\n"
        f"  论证密度 arg_density = {_format_metric(m.arg_density, _arg_density_level)}\n"
        f"  语义重复 Srep = {_format_metric(m.srep, _srep_level)}\n"
        f"  论证结构 reasoning_status = {_format_status(m.reasoning_status)}（{m.reasoning_source or '无说明'}）\n"
        f"  支撑依据 evidence_status = {_format_status(m.evidence_status)}（{m.evidence_source or '无说明'}）"
        for m in req.members
    )
    result = await push_content.analyze_members_batch(
        summary=req.summary,
        transcripts_text=transcripts_text,
        members_metrics_text=members_metrics_text,
    )
    return result
