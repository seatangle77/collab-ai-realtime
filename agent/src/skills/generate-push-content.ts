import type { Transcript } from '../db/queries';
import { generateStructuredPush } from '../http/nlp-client';
import type { Trigger } from './run-reasoning-layer';

const GROUP_SILENCE_FALLBACK_CONTENT = '先聊聊你们各自最关心的是哪个方面？';
const PERSONAL_STAGNATION_WINDOW_MS = 12_000;
const PERSONAL_STAGNATION_MIN_TEXT_LENGTH = 8;
const PERSONAL_STAGNATION_MAX_CANDIDATES = 3;

export interface StructuredAnchor {
  transcriptId: string;
  speakerId: string;
  text: string;
}

export interface GeneratedPushItem {
  targetUserId: string;
  triggerType: Trigger['type'];
  content: string;
  needsPrompt: boolean;
  anchor: StructuredAnchor | null;
}

export interface GeneratePushContentParams {
  sessionId: string;
  triggers: Trigger[];
  transcripts: Transcript[];
  summaryText: string;
  memberIds: string[];
}

interface CandidatePoint {
  transcriptId: string;
  speakerId: string;
  text: string;
}

interface ParsedModelResult {
  needsPrompt: boolean;
  anchor: StructuredAnchor | null;
  content: string;
}

function hasShallowPromptInputs(
  metrics: Record<string, unknown>,
  transcripts: Transcript[],
  userId: string,
): boolean {
  const targetHasQuotes = transcripts.some((item) => item.user_id === userId && item.text?.trim());
  if (!targetHasQuotes) return false;

  const { condA, condB, condC } = getCondFlags(metrics);
  return condA || condB || condC;
}

function getCondFlags(metrics: Record<string, unknown>): { condA: boolean; condB: boolean; condC: boolean } {
  const condA = typeof metrics.srep === 'number' && typeof metrics.info_gain === 'number';
  const condB = typeof metrics.ttr === 'number';
  const condC = typeof metrics.arg_density === 'number'
    || typeof metrics.has_reasoning === 'boolean'
    || typeof metrics.has_evidence === 'boolean';

  return { condA, condB, condC };
}

function selectUnansweredPoints(
  targetUserId: string,
  transcripts: Transcript[],
): CandidatePoint[] {
  const candidates: CandidatePoint[] = [];

  for (let index = transcripts.length - 1; index >= 0; index -= 1) {
    const transcript = transcripts[index];
    const speakerId = transcript.user_id;
    const text = transcript.text?.trim() ?? '';

    if (!speakerId || speakerId === targetUserId) continue;
    if (text.length < PERSONAL_STAGNATION_MIN_TEXT_LENGTH) continue;

    const windowEnd = transcript.end.getTime() + PERSONAL_STAGNATION_WINDOW_MS;
    let targetResponded = false;

    for (let nextIndex = index + 1; nextIndex < transcripts.length; nextIndex += 1) {
      const next = transcripts[nextIndex];
      if (next.start.getTime() > windowEnd) break;

      if (next.user_id === targetUserId && (next.text?.trim() ?? '').length > 0) {
        targetResponded = true;
        break;
      }
    }

    if (targetResponded) continue;

    candidates.push({
      transcriptId: transcript.transcript_id,
      speakerId,
      text,
    });

    if (candidates.length >= PERSONAL_STAGNATION_MAX_CANDIDATES) {
      break;
    }
  }

  return candidates.reverse();
}

function normalizeAnchor(value: unknown): StructuredAnchor | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<{
    transcript_id: string;
    speaker_id: string;
    text: string;
  }>;

  if (
    typeof raw.transcript_id !== 'string'
    || typeof raw.speaker_id !== 'string'
    || typeof raw.text !== 'string'
  ) {
    return null;
  }

  const transcriptId = raw.transcript_id.trim();
  const speakerId = raw.speaker_id.trim();
  const text = raw.text.trim();

  if (!transcriptId || !speakerId || !text) return null;

  return { transcriptId, speakerId, text };
}

async function generateStructured(
  triggerType: 'low_participation' | 'shallow_discussion' | 'group_silence',
  params: {
    summaryText: string;
    transcripts: Transcript[];
    userId: string;
    triggerMetrics: Record<string, unknown>;
    candidatePoints?: CandidatePoint[];
  },
): Promise<ParsedModelResult> {
  const { summaryText, transcripts, userId, triggerMetrics, candidatePoints = [] } = params;
  const result = await generateStructuredPush({
    trigger_type: triggerType,
    summary: summaryText,
    transcripts: transcripts
      .filter((item) => item.text?.trim() && item.user_id)
      .map((item) => ({
        transcript_id: item.transcript_id,
        user_id: item.user_id!,
        speaker_name: item.speaker_name ?? undefined,
        text: item.text!.trim(),
      })),
    user_id: userId,
    trigger_metrics: triggerMetrics,
    candidate_points: candidatePoints.map((item) => ({
      transcript_id: item.transcriptId,
      speaker_id: item.speakerId,
      text: item.text,
    })),
  });

  if (!result.needs_prompt) {
    return { needsPrompt: false, anchor: null, content: '' };
  }

  const anchor = normalizeAnchor(result.anchor);
  const content = result.content.trim();
  if (!anchor || !content) {
    return { needsPrompt: false, anchor: null, content: '' };
  }

  return {
    needsPrompt: true,
    anchor,
    content,
  };
}

async function buildGroupSilenceItems(
  trigger: Trigger,
  transcripts: Transcript[],
  summaryText: string,
): Promise<GeneratedPushItem[]> {
  const generated = await generateStructured('group_silence', {
    summaryText,
    transcripts,
    userId: '',
    triggerMetrics: trigger.triggerMetrics,
  });

  const content = generated.needsPrompt && generated.content
    ? generated.content
    : GROUP_SILENCE_FALLBACK_CONTENT;

  return trigger.targetUsers.map((targetUserId) => ({
    targetUserId,
    triggerType: trigger.type,
    content,
    needsPrompt: true,
    anchor: null,
  }));
}

function isSupportedTrigger(
  trigger: Trigger,
): trigger is Trigger & { type: 'group_silence' | 'shallow_discussion' | 'low_participation' } {
  return trigger.type === 'group_silence'
    || trigger.type === 'shallow_discussion'
    || trigger.type === 'low_participation';
}

export function isStructuredAnchor(value: unknown): value is StructuredAnchor {
  if (!value || typeof value !== 'object') return false;

  const anchor = value as Record<string, unknown>;
  return (
    typeof anchor.transcriptId === 'string'
    && anchor.transcriptId.trim().length > 0
    && typeof anchor.speakerId === 'string'
    && anchor.speakerId.trim().length > 0
    && typeof anchor.text === 'string'
    && anchor.text.trim().length > 0
  );
}

export function validateStructuredAnchor(params: {
  anchor: StructuredAnchor | null;
  transcripts: Transcript[];
  memberIds: string[];
}): StructuredAnchor | null {
  const { anchor, transcripts, memberIds } = params;
  if (!anchor || !isStructuredAnchor(anchor)) return null;
  if (!memberIds.includes(anchor.speakerId)) return null;

  const transcript = transcripts.find((item) => item.transcript_id === anchor.transcriptId);
  if (!transcript) return null;
  if (transcript.user_id !== anchor.speakerId) return null;

  const originalText = transcript.text?.trim() ?? '';
  if (!originalText) return null;
  if (!originalText.includes(anchor.text) && !anchor.text.includes(originalText)) return null;

  return {
    transcriptId: anchor.transcriptId,
    speakerId: anchor.speakerId,
    text: anchor.text,
  };
}

export async function generatePushContent(
  params: GeneratePushContentParams,
): Promise<GeneratedPushItem[]> {
  const { triggers, transcripts, summaryText } = params;
  const results: GeneratedPushItem[] = [];

  for (const trigger of triggers.filter(isSupportedTrigger)) {
    if (trigger.type === 'group_silence') {
      results.push(...await buildGroupSilenceItems(trigger, transcripts, summaryText));
      continue;
    }

    if (trigger.type === 'shallow_discussion') {
      if (!trigger.userId || !hasShallowPromptInputs(trigger.triggerMetrics, transcripts, trigger.userId)) {
        results.push({
          targetUserId: trigger.userId ?? '',
          triggerType: trigger.type,
          content: '',
          needsPrompt: false,
          anchor: null,
        });
        continue;
      }

      const generated = await generateStructured(trigger.type, {
        summaryText,
        transcripts,
        userId: trigger.userId,
        triggerMetrics: trigger.triggerMetrics,
      });
      results.push({
        targetUserId: trigger.userId,
        triggerType: trigger.type,
        content: generated.content,
        needsPrompt: generated.needsPrompt,
        anchor: generated.anchor,
      });
      continue;
    }

    if (!trigger.userId) {
      continue;
    }

    const candidatePoints = selectUnansweredPoints(trigger.userId, transcripts);
    if (candidatePoints.length === 0) {
      results.push({
        targetUserId: trigger.userId,
        triggerType: trigger.type,
        content: '',
        needsPrompt: false,
        anchor: null,
      });
      continue;
    }

    const generated = await generateStructured(trigger.type, {
      summaryText,
      transcripts,
      userId: trigger.userId,
      triggerMetrics: trigger.triggerMetrics,
      candidatePoints,
    });
    results.push({
      targetUserId: trigger.userId,
      triggerType: trigger.type,
      content: generated.content,
      needsPrompt: generated.needsPrompt,
      anchor: generated.anchor,
    });
  }

  return results;
}
