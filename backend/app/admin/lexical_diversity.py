"""Read-only lexical analysis API. No schema, CoI mutations, or persisted analysis."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from ..api_model import ApiModel
from ..db import get_db
from ..analysis.lexical_tokenizer import analyze_with_hanlp
from .deps import require_admin

router = APIRouter(prefix='/api/admin/lexical-diversity', tags=['admin-lexical-diversity'], dependencies=[Depends(require_admin)])


class AnalysisRequest(ApiModel):
    group_ids_by_condition: dict[Literal['no_assistance', 'glasses', 'app_notification'], list[str]]
    task_id: Literal['all', 'lost_at_sea', 'moon_survival', 'winter_survival'] = 'all'


async def load_rows(db, selected):
    ids = [gid for groups in selected.values() for gid in groups]
    if not ids:
        raise HTTPException(422, '请至少选择一个小组')
    if len(ids) != len(set(ids)) or len(ids) > 200:
        raise HTTPException(422, '小组选择重复或超过 200 组')
    # Enforced by PostgreSQL for the entire source read, not merely a naming convention.
    await db.execute(text('SET TRANSACTION READ ONLY'))
    result = await db.execute(text('''
        SELECT g.id AS group_id, g.name AS group_name, g.condition,
               cs.id AS session_id, cs.session_title,
               u.id AS utterance_id, u.order_index, u.content,
               ARRAY(SELECT DISTINCT t.task_id FROM task_score_entries t
                     WHERE t.group_id = g.id ORDER BY t.task_id) AS task_ids
        FROM groups g
        LEFT JOIN chat_sessions cs ON cs.group_id = g.id
        LEFT JOIN coi_utterances u ON u.session_id = cs.id
        WHERE g.id = ANY(:ids)
        ORDER BY g.id, cs.id, u.order_index, u.id
    '''), {'ids': ids})
    rows = [dict(row) for row in result.mappings().all()]
    if {r['group_id'] for r in rows} != set(ids) or any(r['group_id'] not in selected.get(r['condition'], []) for r in rows):
        raise HTTPException(422, '小组不存在或实际条件与筛选条件不一致，请刷新样本')
    return rows


@router.post('/')
async def analyze(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)):
    rows = await load_rows(db, payload.group_ids_by_condition)
    # Release the read transaction before CPU-intensive tokenization.
    await db.rollback()
    try:
        result = await run_in_threadpool(analyze_with_hanlp, rows, payload.task_id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Lexical analysis failed')
        raise HTTPException(503, '词汇分析未完成，请检查 HanLP 模型与分析服务后重试；未修改源数据。') from exc
    result['selection'] = payload.model_dump()
    return result
