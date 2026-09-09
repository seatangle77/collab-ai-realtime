import asyncio
from types import SimpleNamespace
from backend.app.admin.transcript_corrections import list_correctable_transcripts

class Result:
    def __init__(self,rows=(),count=1):self.rows=rows;self.count=count
    def first(self):return self.rows[0] if self.rows else None
    def scalar_one(self):return self.count
    def mappings(self):return self
    def all(self):return self.rows


def test_original_search_uses_original_text_and_trims_large_metadata_in_database():
    queries=[]
    async def execute(query,params=None):
        sql=str(query);queries.append(sql)
        if 'SELECT 1' in sql:return Result([{'exists':1}])
        if 'COUNT(*)' in sql and 'SELECT t.transcript_id' not in sql:return Result()
        if 'SELECT t.transcript_id' in sql:
            return Result([dict(transcript_id='t',session_id='s',group_id='g',speaker_name='甲',original_text='原始识别',effective_text='已修订',is_corrected=True)])
        return Result()
    result=asyncio.run(list_correctable_transcripts('s',page=1,page_size=100,content_view='original',keyword='原始',db=SimpleNamespace(execute=execute)))
    assert result.items[0].original_text=='原始识别'
    count=next(q for q in queries if 'SELECT COUNT(*)' in q)
    assert 'LEFT JOIN LATERAL' not in count
    rows=next(q for q in queries if 'SELECT t.transcript_id' in q)
    assert "COALESCE(t.original_text, t.text, '') ILIKE :keyword" in rows
    assert 'COALESCE(t.original_text, t.text) AS original_text' in rows
    assert "split_part(tc.correction_reason, E'\\n[recording-document-v1]', 1)" in rows
