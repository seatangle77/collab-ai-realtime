from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from backend.app.admin import transcript_alignment as alignment

from backend.app.admin.transcript_alignment import (
    _build_chunks,
    _complete_alignment,
    _deduplicate_matches,
    _alignment_structure_error,
    _partition_existing_corrections,
    _partition_manual_sections,
    _relative_seconds,
    _score_match,
    _split_alignment_groups_by_reference,
    _split_alignment_groups_by_speaker,
    _split_text_by_weights,
    _summary,
    _validate_model_matches,
)
from backend.app.settings import nlp_settings


def _reference(position: int, text: str, start_time: float | None) -> dict:
    return {
        "order_index": position + 1,
        "content": text,
        "start_time": start_time,
        "position": position,
    }


def _live(position: int, text: str, seconds: float | None, corrected: bool = False) -> dict:
    return {
        "transcript_id": f"tr{position + 1}",
        "text": text,
        "speaker_name": "测试成员",
        "relative_seconds": seconds,
        "is_corrected": corrected,
        "has_ai_correction": False,
        "position": position,
    }


class TranscriptAlignmentTests(unittest.TestCase):
    def test_uses_dedicated_max_model(self) -> None:
        self.assertEqual(nlp_settings.transcript_alignment_model, "qwen3-max")
        self.assertEqual(nlp_settings.reasoning_model, "qwen-plus")

    def test_build_chunks_uses_anchor_offset_and_skips_corrected_candidates(self) -> None:
        references = [
            _reference(0, "第一句", 100.0),
            _reference(1, "第二句", 110.0),
        ]
        live_items = [
            _live(0, "第一句", 40.0),
            _live(1, "已经修订", 45.0, corrected=True),
            _live(2, "第二句", 50.0),
            _live(3, "很远的内容", 500.0),
        ]

        chunks = _build_chunks(references, live_items, alignment_offset_seconds=60.0)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(
            [item["transcript_id"] for item in chunks[0]["live_items"]],
            ["tr1", "tr3"],
        )

    def test_old_ai_correction_is_replaceable_but_manual_correction_is_locked(self) -> None:
        references = [_reference(0, "录音准确文字", 10.0)]
        old_ai = _live(0, "旧实时原话", 0.0)
        old_ai["has_ai_correction"] = True
        manual = _live(1, "人工修订前原话", 1.0, corrected=True)

        chunks = _build_chunks(references, [old_ai, manual], alignment_offset_seconds=10.0)

        self.assertEqual(
            [item["transcript_id"] for item in chunks[0]["live_items"]],
            ["tr1"],
        )
        summary = _summary([], references, [old_ai, manual])
        self.assertEqual(summary["replaceable_ai_transcripts"], 1)
        self.assertEqual(summary["skipped_corrected_transcripts"], 1)

    def test_existing_corrections_partition_replaces_only_ai(self) -> None:
        replaceable, blocking = _partition_existing_corrections([
            {
                "transcript_id": "tr1",
                "correction_id": "old-ai",
                "correction_reason": "AI 整场匹配（run=old）",
            },
            {
                "transcript_id": "tr2",
                "correction_id": "manual",
                "correction_reason": "人工核对",
            },
            {
                "transcript_id": "tr3",
                "correction_id": "old-ai",
                "correction_reason": "AI 整场匹配（run=old）",
            },
        ])

        self.assertEqual(replaceable, {"old-ai"})
        self.assertEqual(blocking, {"tr2"})

    def test_valid_match_copies_reference_text_instead_of_model_text(self) -> None:
        references = [_reference(0, "这是人工确认的准确文本。", 20.0)]
        live_items = [
            _live(0, "这是人工", 10.0),
            _live(1, "确认准确文字", 12.0),
        ]
        chunk = {"references": references, "live_items": live_items}
        raw = [{
            "reference_orders": [1],
            "transcript_ids": ["tr1", "tr2"],
            "confidence": 0.98,
            "reason": "内容连续",
            "corrected_text": "模型试图改写的内容",
        }]

        matches = _validate_model_matches(raw, chunk, references, live_items, 10.0)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["corrected_text"], "这是人工确认的准确文本。")
        self.assertEqual(matches[0]["reference_orders"], [1])
        self.assertEqual(matches[0]["transcript_ids"], ["tr1", "tr2"])

    def test_model_match_cannot_cross_speaker_boundary(self) -> None:
        references = [_reference(0, "这是完整内容。", 20.0)]
        live_items = [
            _live(0, "这是", 10.0),
            _live(1, "完整内容", 11.0),
        ]
        live_items[1]["speaker_name"] = "另一位成员"
        chunk = {"references": references, "live_items": live_items}

        matches = _validate_model_matches([{
            "reference_orders": [1],
            "transcript_ids": ["tr1", "tr2"],
            "confidence": 0.98,
            "reason": "模型错误地跨人合并",
        }], chunk, references, live_items, 10.0)

        self.assertEqual(matches, [])

    def test_rejects_non_contiguous_or_corrected_live_matches(self) -> None:
        references = [_reference(0, "准确内容", 10.0)]
        live_items = [
            _live(0, "碎片一", 10.0),
            _live(1, "中间内容", 11.0),
            _live(2, "碎片三", 12.0),
            _live(3, "已修订", 13.0, corrected=True),
        ]
        chunk = {"references": references, "live_items": live_items}
        raw = [
            {"reference_orders": [1], "transcript_ids": ["tr1", "tr3"], "confidence": 0.9},
            {"reference_orders": [1], "transcript_ids": ["tr4"], "confidence": 0.9},
        ]

        matches = _validate_model_matches(raw, chunk, references, live_items, 0.0)

        self.assertEqual(matches, [])

    def test_deduplicate_rejects_reuse_and_backward_mapping(self) -> None:
        base = {
            "reference_text": "准确",
            "transcript_text": "实时",
            "corrected_text": "准确",
            "confidence": 0.9,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "",
            "saved": False,
        }
        matches = [
            {**base, "match_id": "a", "reference_orders": [1], "transcript_ids": ["tr1"], "_reference_position": 0, "_transcript_position": 0},
            {**base, "match_id": "b", "reference_orders": [1], "transcript_ids": ["tr2"], "_reference_position": 0, "_transcript_position": 1},
            {**base, "match_id": "c", "reference_orders": [2], "transcript_ids": ["tr3"], "_reference_position": 1, "_transcript_position": 2},
            {**base, "match_id": "d", "reference_orders": [3], "transcript_ids": ["tr2"], "_reference_position": 2, "_transcript_position": 1},
        ]

        accepted = _deduplicate_matches(matches)

        self.assertEqual([item["match_id"] for item in accepted], ["a", "c"])

    def test_summary_counts_unmatched_and_corrected(self) -> None:
        references = [_reference(0, "一", 1.0), _reference(1, "二", 2.0)]
        live_items = [_live(0, "一", 1.0), _live(1, "二", 2.0), _live(2, "旧", 3.0, True)]
        matches = [{
            "reference_orders": [1],
            "transcript_ids": ["tr1"],
            "confidence_level": "high",
        }]

        result = _summary(matches, references, live_items)

        self.assertEqual(result["high"], 1)
        self.assertEqual(result["unmatched_references"], 1)
        self.assertEqual(result["unmatched_transcripts"], 1)
        self.assertEqual(result["skipped_corrected_transcripts"], 1)

    def test_exact_text_and_time_can_be_high_confidence(self) -> None:
        score, level, distance = _score_match(
            [_reference(0, "完全一致的内容", 30.0)],
            [_live(0, "完全一致的内容", 20.0)],
            model_confidence=0.95,
            alignment_offset_seconds=10.0,
        )

        self.assertGreaterEqual(score, 0.9)
        self.assertEqual(level, "high")
        self.assertEqual(distance, 0.0)

    def test_naive_database_timestamps_are_interpreted_as_utc(self) -> None:
        value = datetime(2026, 9, 7, 1, 0, 35)
        base = datetime(2026, 9, 7, 1, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(_relative_seconds(value, base), 35.0)

    def test_sparse_matches_are_completed_without_unmatched_live_rows(self) -> None:
        references = [
            _reference(0, "第一句", 10.0),
            _reference(1, "第二句", 20.0),
            _reference(2, "第三句", 30.0),
        ]
        live_items = [
            _live(0, "第一", 0.0),
            _live(1, "第二", 10.0),
            _live(2, "第三", 20.0),
            _live(3, "尾部残句", 22.0),
        ]
        seed = {
            "match_id": "seed",
            "reference_orders": [2],
            "transcript_ids": ["tr2"],
            "reference_text": "第二句",
            "transcript_text": "第二",
            "corrected_text": "第二句",
            "confidence": 0.95,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "一致",
            "saved": False,
            "review_required": False,
            "review_reason": "",
        }

        completed, outside = _complete_alignment([seed], references, live_items, 10.0)
        covered = [transcript_id for item in completed for transcript_id in item["transcript_ids"]]
        summary = _summary(completed, references, live_items, outside)

        self.assertEqual(covered, ["tr1", "tr2", "tr3", "tr4"])
        self.assertEqual(outside, [])
        self.assertEqual(summary["unmatched_transcripts"], 0)
        self.assertEqual(summary["organized_transcripts"], 4)
        self.assertGreaterEqual(summary["review_required"], 1)

    def test_live_rows_after_recording_end_are_marked_outside_scope(self) -> None:
        references = [_reference(0, "录音内容", 10.0)]
        live_items = [_live(0, "录音内容", 0.0), _live(1, "录音结束后的聊天", 60.0)]
        seed = {
            "match_id": "seed",
            "reference_orders": [1],
            "transcript_ids": ["tr1"],
            "reference_text": "录音内容",
            "transcript_text": "录音内容",
            "corrected_text": "录音内容",
            "confidence": 0.95,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "一致",
            "saved": False,
            "review_required": False,
            "review_reason": "",
        }

        completed, outside = _complete_alignment([seed], references, live_items, 10.0)
        summary = _summary(completed, references, live_items, outside)

        self.assertEqual(outside, ["tr2"])
        self.assertEqual(summary["organized_transcripts"], 2)
        self.assertEqual(summary["unmatched_transcripts"], 0)

    def test_cross_speaker_group_requires_review(self) -> None:
        references = [_reference(0, "完整内容", 10.0)]
        live_items = [_live(0, "完整", 0.0), _live(1, "内容", 1.0)]
        live_items[1]["speaker_name"] = "另一位成员"
        seed = {
            "match_id": "seed",
            "reference_orders": [1],
            "transcript_ids": ["tr1", "tr2"],
            "reference_text": "完整内容",
            "transcript_text": "完整 内容",
            "corrected_text": "完整内容",
            "confidence": 0.95,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "一致",
            "saved": False,
            "review_required": False,
            "review_reason": "",
        }

        completed, _ = _complete_alignment([seed], references, live_items, 10.0)

        self.assertTrue(completed[0]["review_required"])
        self.assertIn("说话人", completed[0]["review_reason"])

    def test_cross_speaker_group_is_split_without_duplicating_reference(self) -> None:
        references = [
            _reference(0, "甲说的内容。", 10.0),
            _reference(1, "乙说的内容。", 20.0),
        ]
        live_items = [
            _live(0, "甲说内容", 0.0),
            _live(1, "乙说内容", 10.0),
        ]
        live_items[1]["speaker_name"] = "另一位成员"
        coarse = {
            "match_id": "coarse",
            "reference_orders": [1, 2],
            "transcript_ids": ["tr1", "tr2"],
            "reference_text": "",
            "transcript_text": "",
            "corrected_text": "",
            "confidence": 0.9,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "粗分组",
            "saved": False,
            "review_required": True,
            "review_reason": "这组跨越了说话人边界，请确认分组",
        }

        by_reference = _split_alignment_groups_by_reference(
            [coarse], references, live_items, alignment_offset_seconds=10.0,
        )
        result = _split_alignment_groups_by_speaker(
            by_reference, references, live_items, alignment_offset_seconds=10.0,
        )

        self.assertEqual([item["reference_orders"] for item in result], [[1], [2]])
        self.assertEqual([item["transcript_ids"] for item in result], [["tr1"], ["tr2"]])
        self.assertTrue(all(not item["review_required"] for item in result))

    def test_one_reference_row_is_split_across_speakers_without_original_gap(self) -> None:
        references = [_reference(0, "甲说的准确内容。", 10.0)]
        live_items = [
            _live(0, "甲说的内容", 0.0),
            _live(1, "乙插话", 8.0),
        ]
        live_items[1]["speaker_name"] = "另一位成员"
        coarse = {
            "match_id": "coarse",
            "reference_orders": [1],
            "transcript_ids": ["tr1", "tr2"],
            "reference_text": "",
            "transcript_text": "",
            "corrected_text": "",
            "confidence": 0.7,
            "confidence_level": "medium",
            "time_distance_seconds": 0.0,
            "reason": "粗分组",
            "saved": False,
            "review_required": True,
            "review_reason": "这组跨越了说话人边界，请确认分组",
        }

        result = _split_alignment_groups_by_speaker(
            [coarse], references, live_items, alignment_offset_seconds=10.0,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual([item["transcript_ids"] for item in result], [["tr1"], ["tr2"]])
        self.assertEqual(
            "".join(item["corrected_text"] for item in result),
            "甲说的准确内容。",
        )
        self.assertEqual(_summary(result, references, live_items)["unmatched_transcripts"], 0)
        self.assertIsNone(_alignment_structure_error(result, references, live_items, []))

    def test_speaker_text_split_prefers_aligned_sentence_boundary(self) -> None:
        result = _split_text_by_weights(
            "甲提出了第一个方案。乙表示时间可能不够。",
            [7, 8],
            ["甲提出第一个方案", "乙说时间不够"],
        )

        self.assertEqual(result, ["甲提出了第一个方案。", "乙表示时间可能不够。"])

    def test_speaker_text_split_never_creates_whitespace_only_slice(self) -> None:
        result = _split_text_by_weights(
            "甲          乙丙",
            [1, 1, 1],
            ["甲", "乙", "丙"],
        )

        self.assertTrue(all(item.strip() for item in result))
        self.assertEqual("".join(result).replace(" ", ""), "甲乙丙")

    def test_no_model_matches_never_become_automatic_full_revision(self) -> None:
        references = [
            _reference(0, "甲说的内容。", 10.0),
            _reference(1, "乙说的内容。", 20.0),
        ]
        live_items = [
            _live(0, "甲说内容", 0.0),
            _live(1, "乙说内容", 10.0),
        ]
        live_items[1]["speaker_name"] = "另一位成员"

        completed, _ = _complete_alignment([], references, live_items, 10.0)
        by_reference = _split_alignment_groups_by_reference(
            completed, references, live_items, alignment_offset_seconds=10.0,
        )
        result = _split_alignment_groups_by_speaker(
            by_reference, references, live_items, alignment_offset_seconds=10.0,
        )

        self.assertEqual(result, [])
        self.assertEqual(_summary(result, references, live_items)["unmatched_transcripts"], 2)
        self.assertIsNotNone(_alignment_structure_error(result, references, live_items, []))

    def test_manual_merged_prefix_is_not_reassigned_to_remaining_live_row(self) -> None:
        refs = [_reference(i, text, i * 100.0) for i, text in enumerate(["甲内容", "乙内容", "丙内容"])]
        live = [_live(i, text, i * 100.0, corrected=i < 2) for i, text in enumerate(["甲", "乙", "丙"])]
        for item in live[:2]:
            item.update(existing_correction_id="manual", manual_corrected_text="甲内容。\n乙内容！")
        sections = _partition_manual_sections(refs, live, 0)
        self.assertEqual(len(sections), 1)
        section = sections[0]
        self.assertEqual([item["order_index"] for item in section["references"]], [3])
        self.assertEqual([item["transcript_id"] for item in section["live_items"]], ["tr3"])
        seed = _validate_model_matches(
            [{"reference_orders": [3], "transcript_ids": ["tr3"], "confidence": .95}],
            section, section["references"], section["live_items"], 0,
        )
        matches, outside = _complete_alignment(seed, section["references"], section["live_items"], 0)
        self.assertEqual([item["corrected_text"] for item in matches], ["丙内容"])
        self.assertIsNone(_alignment_structure_error(matches, section["references"], live, outside))

    def test_manual_middle_splits_ai_work_into_independent_sections(self) -> None:
        refs = [_reference(i, text, i * 100.0) for i, text in enumerate(["前文", "人工正文", "后文"])]
        live = [_live(i, text, i * 100.0, corrected=i == 1) for i, text in enumerate(["前", "中", "后"])]
        live[1].update(existing_correction_id="manual", manual_corrected_text="人工正文")
        sections = _partition_manual_sections(refs, live, 0)
        self.assertEqual([[r["order_index"] for r in s["references"]] for s in sections], [[1], [3]])
        self.assertEqual([[r["transcript_id"] for r in s["live_items"]] for s in sections], [["tr1"], ["tr3"]])

    def test_uncertain_manual_text_stops_instead_of_guessing_range(self) -> None:
        refs = [_reference(0, "录音原话", 0), _reference(1, "剩余", 100)]
        live = [_live(0, "原话", 0, True), _live(1, "剩余", 100)]
        live[0].update(existing_correction_id="manual", manual_corrected_text="人工重新概括过的内容")
        with self.assertRaisesRegex(ValueError, "无法明确确定"):
            _partition_manual_sections(refs, live, 0)

    def test_repeated_manual_text_is_ambiguous(self) -> None:
        refs = [_reference(0, "相同", 0), _reference(1, "相同", 10)]
        live = [_live(0, "相同", 0, True), _live(1, "相同", 10)]
        live[0].update(existing_correction_id="manual", manual_corrected_text="相同")
        with self.assertRaises(ValueError):
            _partition_manual_sections(refs, live, 0)

    def test_missing_time_candidates_do_not_fall_back_to_distant_rows(self) -> None:
        chunks = _build_chunks([_reference(0, "早期", 0)], [_live(0, "后期", 200)], 0)
        self.assertEqual(chunks[0]["live_items"], [])

    def test_recording_only_prefix_stays_unmatched(self) -> None:
        refs = [_reference(0, "已处理", 0), _reference(1, "剩余", 100)]
        live = [_live(0, "剩余", 100)]
        chunk = {"references": refs, "live_items": live}
        seed = _validate_model_matches(
            [{"reference_orders": [2], "transcript_ids": ["tr1"], "confidence": .95}],
            chunk, refs, live, 0,
        )
        matches, outside = _complete_alignment(seed, refs, live, 0)
        self.assertEqual([m["corrected_text"] for m in matches], ["剩余"])
        self.assertIsNotNone(_alignment_structure_error(matches, refs, live, outside))

    def test_model_cannot_override_anchor_time_with_a_distant_match(self) -> None:
        refs = [_reference(0, "相同文字", 0)]
        live = [_live(0, "相同文字", 200)]
        chunk = {"references": refs, "live_items": live}
        matches = _validate_model_matches(
            [{"reference_orders": [1], "transcript_ids": ["tr1"], "confidence": 1}],
            chunk, refs, live, 0,
        )
        self.assertEqual(matches, [])

    def test_completion_requires_manual_boundaries_to_be_resolved_first(self) -> None:
        with self.assertRaisesRegex(ValueError, "人工修订边界"):
            _complete_alignment([], [_reference(0, "人工", 0)], [_live(0, "人工", 0, True)], 0)

    def test_anchor_after_manual_section_keeps_original_positions(self) -> None:
        refs = [_reference(5, "后续", 500)]
        live = [_live(8, "后续", 400)]
        sections = _partition_manual_sections(refs, live, 100)
        self.assertEqual(sections, [{"references": refs, "live_items": live}])

    def test_structure_check_rejects_missing_middle_transcript(self) -> None:
        references = [_reference(0, "完整内容。", 10.0)]
        live_items = [_live(0, "完整", 0.0), _live(1, "内容", 1.0)]
        incomplete = [{
            "reference_orders": [1],
            "transcript_ids": ["tr1"],
            "corrected_text": "完整内容。",
        }]

        self.assertEqual(
            _alignment_structure_error(incomplete, references, live_items, []),
            "录音范围内仍有实时转写未完成修订",
        )

    def test_structure_check_rejects_blank_corrected_text(self) -> None:
        references = [_reference(0, "准确内容。", 10.0)]
        live_items = [_live(0, "实时内容", 0.0)]
        blank = [{
            "reference_orders": [1],
            "transcript_ids": ["tr1"],
            "corrected_text": "   ",
        }]

        self.assertEqual(
            _alignment_structure_error(blank, references, live_items, []),
            "存在空白修订文字",
        )

    def test_structure_check_rejects_untracked_reference_duplication(self) -> None:
        references = [_reference(0, "完整内容。", 10.0)]
        live_items = [_live(0, "完整", 0.0), _live(1, "内容", 1.0)]
        duplicated = [
            {"reference_orders": [1], "transcript_ids": ["tr1"], "corrected_text": "完整内容。"},
            {"reference_orders": [1], "transcript_ids": ["tr2"], "corrected_text": "完整内容。"},
        ]

        self.assertEqual(
            _alignment_structure_error(duplicated, references, live_items, []),
            "准确录音文字被重复分配到多个修订段落",
        )

    def test_large_group_is_split_back_to_recording_utterance_boundaries(self) -> None:
        references = [
            _reference(0, "录音第一句。", 10.0),
            _reference(1, "录音第二句。", 20.0),
            _reference(2, "录音第三句。", 30.0),
        ]
        live_items = [
            _live(0, "第一", 0.0),
            _live(1, "句", 1.0),
            _live(2, "第二", 10.0),
            _live(3, "句", 11.0),
            _live(4, "第三", 20.0),
            _live(5, "句", 21.0),
        ]
        coarse = {
            "match_id": "coarse",
            "reference_orders": [1, 2, 3],
            "transcript_ids": ["tr1", "tr2", "tr3", "tr4", "tr5", "tr6"],
            "reference_text": "",
            "transcript_text": "",
            "corrected_text": "",
            "confidence": 0.9,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "粗分组",
            "saved": False,
            "review_required": False,
            "review_reason": "",
        }

        result = _split_alignment_groups_by_reference([coarse], references, live_items, 10.0)

        self.assertEqual([item["reference_orders"] for item in result], [[1], [2], [3]])
        self.assertEqual([item["transcript_ids"] for item in result], [
            ["tr1", "tr2"], ["tr3", "tr4"], ["tr5", "tr6"],
        ])
        self.assertEqual([item["corrected_text"] for item in result], [
            "录音第一句。", "录音第二句。", "录音第三句。",
        ])

    def test_one_live_row_keeps_multiple_recording_lines_visually_separate(self) -> None:
        references = [_reference(0, "第一句。", 10.0), _reference(1, "第二句。", 12.0)]
        live_items = [_live(0, "第一句第二句", 0.0)]
        coarse = {
            "match_id": "coarse",
            "reference_orders": [1, 2],
            "transcript_ids": ["tr1"],
            "reference_text": "",
            "transcript_text": "",
            "corrected_text": "",
            "confidence": 0.9,
            "confidence_level": "high",
            "time_distance_seconds": 0.0,
            "reason": "粗分组",
            "saved": False,
            "review_required": False,
            "review_reason": "",
        }

        result = _split_alignment_groups_by_reference([coarse], references, live_items, 10.0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["corrected_text"], "第一句。\n第二句。")


class TranscriptAlignmentOfflineFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_failure_does_not_create_a_saveable_full_revision(self) -> None:
        refs = [_reference(0, "正文", 0)]
        live = [_live(0, "正文", 0)]
        run = {"run_id": "offline", "failed_chunks": [], "total_tokens": 0}
        with patch.object(alignment, "_load_run", AsyncMock(return_value=run)), \
             patch.object(alignment, "_store_run", AsyncMock()), \
             patch.object(alignment, "AsyncOpenAI", Mock()), \
             patch.object(alignment, "logger", Mock()), \
             patch.object(alignment, "_call_alignment_model", AsyncMock(side_effect=ValueError("offline failure"))):
            await alignment._execute_alignment_run("offline", refs, live, 0)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["matches"], [])

    async def test_ambiguous_manual_range_stops_before_background_ai_starts(self) -> None:
        refs = [_reference(0, "原文", 0), _reference(1, "后文", 100)]
        live = [_live(0, "原文", 0, True), _live(1, "后文", 100)]
        live[0].update(existing_correction_id="manual", manual_corrected_text="改写后的内容")
        tasks = Mock()
        payload = alignment.StartAlignmentRunIn(anchor=alignment.AlignmentAnchorIn(
            transcript_id="tr1", transcript_relative_seconds=0,
            reference_order=1, reference_start_time=0,
        ))
        with patch.object(alignment.nlp_settings, "qwen_api_key", "offline-placeholder"), \
             patch.object(alignment, "_load_alignment_source", AsyncMock(return_value=({}, refs, live))), \
             patch.object(alignment, "_store_run", AsyncMock()) as store:
            with self.assertRaisesRegex(alignment.HTTPException, "无法明确确定"):
                await alignment.start_alignment_run("offline", payload, tasks, Mock())
            store.assert_not_called()
        tasks.add_task.assert_not_called()

    async def test_full_pipeline_preserves_manual_middle_and_only_sends_other_text(self) -> None:
        refs = [_reference(i, text, i * 100.0) for i, text in enumerate(["前文", "人工正文", "后文"])]
        live = [_live(i, text, i * 100.0, i == 1) for i, text in enumerate(["前文", "人工", "后文"])]
        live[1].update(existing_correction_id="manual", manual_corrected_text="人工正文")
        run = {"run_id": "offline", "failed_chunks": [], "total_tokens": 0}
        async def model(_client, chunk, _offset):
            self.assertNotIn(2, [r["order_index"] for r in chunk["references"]])
            return [{"reference_orders": [chunk["references"][0]["order_index"]],
                     "transcript_ids": [chunk["live_items"][0]["transcript_id"]],
                     "confidence": .99}], 0
        with patch.object(alignment, "_load_run", AsyncMock(return_value=run)), \
             patch.object(alignment, "_store_run", AsyncMock()), \
             patch.object(alignment, "AsyncOpenAI", Mock()), \
             patch.object(alignment, "_call_alignment_model", side_effect=model):
            await alignment._execute_alignment_run("offline", refs, live, 0)
        self.assertEqual(run["status"], "completed")
        self.assertEqual([m["corrected_text"] for m in run["matches"]], ["前文", "后文"])
        self.assertEqual([m["_section_index"] for m in run["matches"]], [0, 1])
        self.assertEqual(run["summary"]["skipped_corrected_transcripts"], 1)
        self.assertEqual(run["summary"]["unmatched_references"], 0)

    async def test_start_passes_only_content_after_both_selected_anchors(self) -> None:
        refs = [_reference(0, "之前", 10), _reference(1, "之后", 110)]
        live = [_live(0, "之前", 0), _live(1, "之后", 100)]
        tasks = Mock()
        payload = alignment.StartAlignmentRunIn(anchor=alignment.AlignmentAnchorIn(
            transcript_id="tr2", transcript_relative_seconds=100,
            reference_order=2, reference_start_time=110,
        ))
        with patch.object(alignment.nlp_settings, "qwen_api_key", "offline-placeholder"), \
             patch.object(alignment, "_load_alignment_source", AsyncMock(return_value=({}, refs, live))), \
             patch.object(alignment, "_store_run", AsyncMock()):
            await alignment.start_alignment_run("offline", payload, tasks, Mock())
        args = tasks.add_task.call_args.args
        self.assertEqual(args[2], refs[1:])
        self.assertEqual(args[3], live[1:])
        self.assertEqual(args[4], 10)

    async def test_old_preview_cannot_reach_database_on_save(self) -> None:
        db = Mock()
        with patch.object(alignment, "_load_run", AsyncMock(return_value={"status": "completed"})):
            with self.assertRaisesRegex(alignment.HTTPException, "旧的对齐规则"):
                await alignment.save_alignment_run("offline", SimpleNamespace(match_ids=[]), db)
        db.execute.assert_not_called()

    async def test_changed_manual_correction_blocks_save_before_any_write(self) -> None:
        run = {"logic_version": alignment.ALIGNMENT_LOGIC_VERSION,
               "protected_manual": [{"transcript_id": "tr1", "correction_id": "manual", "corrected_text": "旧人工内容"}]}
        rows = Mock()
        rows.mappings.return_value.all.return_value = [
            {"transcript_id": "tr1", "correction_id": "manual", "corrected_text": "新人工内容"}]
        db = SimpleNamespace(execute=AsyncMock(return_value=rows))
        with patch.object(alignment, "_load_run", AsyncMock(return_value=run)):
            with self.assertRaisesRegex(alignment.HTTPException, "人工修订已变化"):
                await alignment.save_alignment_run("offline", SimpleNamespace(match_ids=[]), db)
        self.assertEqual(db.execute.await_count, 1)
        self.assertTrue(str(db.execute.call_args.args[0]).lstrip().startswith("SELECT"))

    async def test_boundary_merge_cannot_cross_manual_section(self) -> None:
        run = {"status": "completed", "matches": [
            {"match_id": "a", "_section_index": 0}, {"match_id": "b", "_section_index": 1}]}
        db = Mock()
        with patch.object(alignment, "_load_run", AsyncMock(return_value=run)):
            with self.assertRaisesRegex(alignment.HTTPException, "不能跨越人工修订"):
                await alignment.resolve_alignment_boundary("offline", SimpleNamespace(match_id="a", action="next"), db)
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
