# -*- coding: utf-8 -*-
import logging

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.6


class SpeakerIdentifier:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.encoder = VoiceEncoder()                    # 加载预训练声纹模型
        self.ref_embeds: dict[str, np.ndarray] = {}     # user_id → 256维向量

    async def load_profiles(self, db: AsyncSession, user_ids: list[str]) -> None:
        """从 DB 加载指定用户的声纹 embedding 到内存"""
        if not user_ids:
            logger.warning("[SpeakerIdentifier] session=%s 未传入 user_ids，跳过加载", self.session_id)
            return

        result = await db.execute(
            text("""
                SELECT user_id, voice_embedding
                FROM user_voice_profiles
                WHERE user_id = ANY(:user_ids)
                  AND embedding_status = 'ready'
            """),
            {"user_ids": user_ids},
        )
        rows = result.mappings().all()

        for row in rows:
            raw = row["voice_embedding"]
            if isinstance(raw, list):
                # 标准格式：直接存的 list[float]
                self.ref_embeds[row["user_id"]] = np.array(raw, dtype=np.float32)
            elif isinstance(raw, dict) and "vector" in raw:
                # 兼容格式：{"vector": list[float]}
                self.ref_embeds[row["user_id"]] = np.array(raw["vector"], dtype=np.float32)
            else:
                logger.warning(
                    "[SpeakerIdentifier] user_id=%s embedding 格式不支持，跳过",
                    row["user_id"],
                )

        loaded = list(self.ref_embeds.keys())
        logger.info(
            "[SpeakerIdentifier] session=%s 加载声纹 %d 条: %s",
            self.session_id, len(loaded), loaded,
        )

    def identify(self, audio_bytes: bytes) -> tuple[str, float]:
        """
        输入 PCM 16bit 16kHz bytes，返回 (user_id, confidence)。
        无法识别时返回 ("unknown", similarity)。
        """
        # 未加载声纹 → 直接返回 unknown
        if not self.ref_embeds:
            return "unknown", 0.0

        # 音频为空 → 直接返回 unknown
        wav_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        if len(wav_int16) == 0:
            return "unknown", 0.0

        # PCM bytes → float32 波形
        wav_float32 = wav_int16.astype(np.float32) / 32768.0
        wav = preprocess_wav(wav_float32, source_sr=16000)

        # 提取当前片段 embedding
        cur_embed = self.encoder.embed_utterance(wav)

        # 余弦相似度匹配所有参考声纹
        best_user, best_sim = "unknown", 0.0
        for user_id, ref_embed in self.ref_embeds.items():
            # 跳过无效 embedding（None 或非 ndarray）
            if ref_embed is None or not isinstance(ref_embed, np.ndarray):
                logger.warning(
                    "[SpeakerIdentifier] user_id=%s embedding 无效，跳过", user_id
                )
                continue
            sim = float(
                np.dot(cur_embed, ref_embed) /
                (np.linalg.norm(cur_embed) * np.linalg.norm(ref_embed) + 1e-9)
            )
            if sim > best_sim:
                best_user, best_sim = user_id, sim

        # 低于阈值 → unknown
        if best_sim < SIMILARITY_THRESHOLD:
            logger.debug(
                "[SpeakerIdentifier] session=%s 相似度 %.3f 低于阈值，标记 unknown",
                self.session_id, best_sim,
            )
            return "unknown", best_sim

        logger.debug(
            "[SpeakerIdentifier] session=%s 识别为 %s，相似度 %.3f",
            self.session_id, best_user, best_sim,
        )
        return best_user, best_sim

    def has_profiles(self) -> bool:
        """是否已加载声纹，可供 audio_service 判断是否跳过识别"""
        return len(self.ref_embeds) > 0

    def clear(self) -> None:
        """会话结束时释放内存"""
        self.ref_embeds.clear()
        logger.info("[SpeakerIdentifier] session=%s 声纹缓存已清理", self.session_id)
