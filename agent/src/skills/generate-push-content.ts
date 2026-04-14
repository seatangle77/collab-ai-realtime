import axios from 'axios';
import { config, hasQwenConfig } from '../config';
import type { Transcript } from '../db/queries';
import { createLogger } from '../logger';
import type { Trigger } from './run-reasoning-layer';

const logger = createLogger('generate-push-content');

const GROUP_SILENCE_FIXED_CONTENT = '小组已沉默超过30秒，大家可以继续讨论～';
const PERSONAL_STAGNATION_WINDOW_MS = 12_000;
const PERSONAL_STAGNATION_MIN_TEXT_LENGTH = 8;
const PERSONAL_STAGNATION_MAX_CANDIDATES = 3;
const MAX_CONTENT_LENGTH = 30;

const SYSTEM_PROMPT = `你是一个小组讨论协作引导助手。

硬性规则：
1. 不要把讨论改写成知识问答、购买建议、泛化推荐或价值排序。生成的问题必须是对已有发言的续接，而不是话题扩展。
2. content 必须能被视为对 anchor 的直接追问：要求理由、条件、例子、边界，或对某个已出现观点表态；不能脱离 anchor 单独成立。
3. anchor 必须是【发言记录】里的原话，不能改写，不能合并多句，必须同时返回说话人 ID。
4. 只返回 JSON，不要输出任何解释。`;

interface StructuredAnchorPayload {
  transcript_id: string;
  speaker_id: string;
  text: string;
}

interface QwenMessage {
  role: 'system' | 'user';
  content: string;
}

interface QwenChatChoice {
  message?: {
    content?: string | Array<{ type?: string; text?: string }>;
  };
}

interface QwenChatCompletionResponse {
  choices?: QwenChatChoice[];
}

interface QwenGeneration {
  output_text?: string;
  content?: string;
  text?: string;
}

interface QwenResponseOutputItem {
  content?: Array<{ type?: string; text?: string }>;
}

interface QwenResponsesApiResponse {
  output_text?: string;
  output?: QwenResponseOutputItem[];
}

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

function formatTranscriptLine(transcript: Transcript): string {
  return `${transcript.user_id ?? 'unknown'} | ${transcript.transcript_id} | ${(transcript.text ?? '').trim()}`;
}

function transcriptTextForPrompt(transcripts: Transcript[]): string {
  return transcripts
    .filter((item) => item.text?.trim())
    .map(formatTranscriptLine)
    .join('\n');
}

function getCondFlags(metrics: Record<string, unknown>): { condA: boolean; condB: boolean; condC: boolean } {
  const condA = typeof metrics.srep === 'number' && typeof metrics.info_gain === 'number';
  const condB = typeof metrics.ttr === 'number';
  const condC = typeof metrics.arg_density === 'number'
    || typeof metrics.has_reasoning === 'boolean'
    || typeof metrics.has_evidence === 'boolean';

  return { condA, condB, condC };
}

function formatPercent(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0';
  return (Math.round(value * 1000) / 10).toString();
}

function numberOrZero(value: unknown, digits = 3): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0';
  return value.toFixed(digits);
}

function buildShallowPrompt(trigger: Trigger, transcripts: Transcript[], summaryText: string): string | null {
  if (!trigger.userId) return null;

  const targetQuotes = transcripts
    .filter((item) => item.user_id === trigger.userId && item.text?.trim())
    .map(formatTranscriptLine)
    .join('\n');

  if (!targetQuotes) return null;

  const metrics = trigger.triggerMetrics;
  const { condA, condB, condC } = getCondFlags(metrics);
  const issueLabels: string[] = [];
  const instructionParts: string[] = [];

  if (condA) {
    issueLabels.push('判断重复');
    instructionParts.push('可以追问这个判断的前提是什么，或者在什么情况下不成立。');
  }
  if (condB) {
    issueLabels.push('表达模糊');
    instructionParts.push('也可以追问这句话具体指的是什么情况。');
  }
  if (condC) {
    issueLabels.push('缺乏论证');
    instructionParts.push('也可以追问这个判断的依据是什么，或者能否举一个例子支持它。');
  }

  if (issueLabels.length === 0) return null;

  const diagnosisParts: string[] = [];
  if (condA) {
    diagnosisParts.push(
      `Srep=${numberOrZero(metrics.srep)}（超过0.65）且信息增益=${numberOrZero(metrics.info_gain)}（低于0.3）`,
    );
  }
  if (condB) {
    diagnosisParts.push(`TTR=${numberOrZero(metrics.ttr)}（低于0.4）`);
  }
  if (condC) {
    diagnosisParts.push(`论证词密度=${numberOrZero(metrics.arg_density)}（低于0.02）`);
  }

  const diagnosisText = `该成员同时存在${issueLabels.map((label) => `“${label}”`).join('、')}等问题。${diagnosisParts.join('，')}。`;
  const taskInstruction = `请从【目标成员发言】里选一句最能体现这些问题的话，优先选最近的判断句。${instructionParts.join('')}只能围绕他说过的那句话续接，不能引入新话题。`;

  return [
    '【当前摘要】',
    summaryText,
    '',
    '【最近发言（全体，按时间顺序，格式：speaker_id | transcript_id | 原话）】',
    transcriptTextForPrompt(transcripts),
    '',
    '【检测结论】',
    diagnosisText,
    '',
    '【目标成员发言】',
    targetQuotes,
    '',
    '【你的任务】',
    taskInstruction,
    '',
    '返回格式（严格 JSON）：',
    '{',
    '  "needs_prompt": true/false,',
    '  "anchor": {',
    '    "transcript_id": "原话对应的 transcript id",',
    '    "speaker_id": "说话人 user_id",',
    '    "text": "原话原文"',
    '  },',
    `  "content": "生成的建议，不超过${MAX_CONTENT_LENGTH}字"`,
    '}',
  ].join('\n');
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

function buildPersonalStagnationPrompt(
  trigger: Trigger,
  transcripts: Transcript[],
  summaryText: string,
  candidatePoints: CandidatePoint[],
): string {
  const diagnosisText = `该成员过去120秒发言占比 ${formatPercent(trigger.triggerMetrics.speaking_ratio)}%，低于15%，参与明显减少。`;
  const taskInstruction = `以下是其他成员说过但 ${trigger.userId ?? '该成员'} 没有回应的发言（候选追问点）。请从候选点中选一条，问 ${trigger.userId ?? '该成员'} 对这个观点怎么看或是否同意。anchor 必须来自候选追问点里的某一条，不能自己另找角度。如果候选点都不适合追问，返回 needs_prompt: false。`;
  const formattedCandidates = candidatePoints
    .map((item) => `${item.speakerId} | ${item.transcriptId} | ${item.text}`)
    .join('\n');

  return [
    '【当前摘要】',
    summaryText,
    '',
    '【最近发言（全体，按时间顺序，格式：speaker_id | transcript_id | 原话）】',
    transcriptTextForPrompt(transcripts),
    '',
    '【检测结论】',
    diagnosisText,
    '',
    '【候选追问点】',
    formattedCandidates,
    '',
    '【你的任务】',
    taskInstruction,
    '',
    '返回格式（严格 JSON）：',
    '{',
    '  "needs_prompt": true/false,',
    '  "anchor": {',
    '    "transcript_id": "原话对应的 transcript id",',
    '    "speaker_id": "说话人 user_id",',
    '    "text": "原话原文"',
    '  },',
    `  "content": "生成的建议，不超过${MAX_CONTENT_LENGTH}字"`,
    '}',
  ].join('\n');
}

function normalizeAnchor(value: unknown): StructuredAnchor | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Partial<StructuredAnchorPayload>;

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

function parseJsonObject(text: string): Record<string, unknown> | null {
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    const match = text.match(/\{[\s\S]*\}/);
    if (!match) return null;

    try {
      return JSON.parse(match[0]) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
}

function extractResponsesText(data: QwenResponsesApiResponse): string {
  if (typeof data.output_text === 'string' && data.output_text.trim()) {
    return data.output_text.trim();
  }

  for (const item of data.output ?? []) {
    for (const content of item.content ?? []) {
      if (content.type === 'output_text' && content.text?.trim()) {
        return content.text.trim();
      }
      if (content.text?.trim()) {
        return content.text.trim();
      }
    }
  }

  return '';
}

async function callQwen(messages: QwenMessage[]): Promise<string> {
  const headers = {
    Authorization: `Bearer ${config.qwen.apiKey}`,
    'Content-Type': 'application/json',
  };

  try {
    const response = await axios.post<QwenResponsesApiResponse>(
      `${config.qwen.baseUrl.replace(/\/$/, '')}/responses`,
      {
        model: config.qwen.model,
        input: messages.map((message) => ({
          role: message.role,
          content: [{ type: 'input_text', text: message.content }],
        })),
      },
      { headers, timeout: 30_000 },
    );

    const text = extractResponsesText(response.data);
    if (text) return text;
  } catch (err) {
    logger.warn('Qwen responses API failed, fallback to chat completions', {
      message: (err as Error).message,
    });
  }

  const response = await axios.post<QwenChatCompletionResponse>(
    `${config.qwen.baseUrl.replace(/\/$/, '')}/chat/completions`,
    {
      model: config.qwen.model,
      messages,
      response_format: { type: 'json_object' },
    },
    { headers, timeout: 30_000 },
  );

  const content = response.data.choices?.[0]?.message?.content;
  if (typeof content === 'string') return content.trim();
  if (Array.isArray(content)) {
    return content.map((part) => part.text ?? '').join('').trim();
  }

  return '';
}

async function generateFromPrompt(prompt: string): Promise<ParsedModelResult> {
  if (!hasQwenConfig()) {
    logger.warn('Qwen config is missing, skip generation for current prompt');
    return { needsPrompt: false, anchor: null, content: '' };
  }

  try {
    const raw = await callQwen([
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: prompt },
    ]);
    const parsed = parseJsonObject(raw);

    if (!parsed) {
      return { needsPrompt: false, anchor: null, content: '' };
    }

    const needsPrompt = parsed.needs_prompt === true;
    const anchor = normalizeAnchor(parsed.anchor);
    const content = typeof parsed.content === 'string' ? parsed.content.trim() : '';

    if (!needsPrompt) {
      return { needsPrompt: false, anchor: null, content: '' };
    }

    if (!anchor || !content || content.length > MAX_CONTENT_LENGTH) {
      return { needsPrompt: false, anchor: null, content: '' };
    }

    return { needsPrompt: true, anchor, content };
  } catch (err) {
    logger.error('generate push content failed', { message: (err as Error).message });
    return { needsPrompt: false, anchor: null, content: '' };
  }
}

function buildGroupSilenceItems(trigger: Trigger): GeneratedPushItem[] {
  return trigger.targetUsers.map((targetUserId) => ({
    targetUserId,
    triggerType: trigger.type,
    content: GROUP_SILENCE_FIXED_CONTENT,
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
      results.push(...buildGroupSilenceItems(trigger));
      continue;
    }

    if (trigger.type === 'shallow_discussion') {
      const prompt = buildShallowPrompt(trigger, transcripts, summaryText);
      if (!prompt || !trigger.userId) {
        results.push({
          targetUserId: trigger.userId ?? '',
          triggerType: trigger.type,
          content: '',
          needsPrompt: false,
          anchor: null,
        });
        continue;
      }

      const generated = await generateFromPrompt(prompt);
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

    const prompt = buildPersonalStagnationPrompt(trigger, transcripts, summaryText, candidatePoints);
    const generated = await generateFromPrompt(prompt);
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
