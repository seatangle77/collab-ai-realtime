"""
NLP 微服务路由
- 前缀：/api/nlp
- 鉴权：X-Admin-Token（复用现有 require_admin）
- 7 个接口：segment / embed / similarity / tfidf / has_reasoning / generate_push / generate_summary
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..admin.deps import require_admin
from . import embedder, similarity, segmenter, tfidf, reasoning, push_content, summary

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


# ── 4. tfidf ─────────────────────────────────────────────────────────────────

class TfidfRequest(BaseModel):
    member_texts: dict[str, str]          # {user_id: 发言文本}
    top_n: int = Field(default=5, ge=1, le=20)


class TfidfResponse(BaseModel):
    keywords: list[str]
    member_keyword_contexts: dict[str, dict[str, str]]


@router.post("/tfidf", response_model=TfidfResponse)
def extract_tfidf(req: TfidfRequest, _: bool = Depends(require_admin)):
    return tfidf.extract_tfidf(req.member_texts, req.top_n)


# ── 5. has_reasoning ─────────────────────────────────────────────────────────

class ReasoningRequest(BaseModel):
    text: str


class ReasoningResponse(BaseModel):
    has_reasoning: bool
    has_evidence: bool
    method: str                           # "rule" 或 "llm"


@router.post("/has_reasoning", response_model=ReasoningResponse)
def check_reasoning(req: ReasoningRequest, _: bool = Depends(require_admin)):
    return reasoning.has_reasoning(req.text)


# ── 6. generate_push ──────────────────────────────────────────────────────────

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


# ── 7. generate_summary ───────────────────────────────────────────────────────

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
