import { runReasoningLayer } from '../src/skills/run-reasoning-layer';
import type { PipelineResult } from '../src/skills/run-perception-pipeline';

// ── 基础数据 ──────────────────────────────────────────────────────────────────

const MEMBERS = ['uA', 'uB', 'uC'];

/** 构造一个所有指标"正常"的基线 PipelineResult，按需覆盖 */
function baseResult(overrides: Partial<PipelineResult> = {}): PipelineResult {
  return {
    speakingRatios:  { uA: 0.4, uB: 0.35, uC: 0.25 },
    silenceSeconds:  { uA: 5,   uB: 5,    uC: 5 },
    ttrs:            { uA: 0.6, uB: 0.6,  uC: 0.6 },
    argDensities:    { uA: 0.1, uB: 0.1,  uC: 0.1 },
    sreps:           { uA: 0.4, uB: 0.4,  uC: 0.4 },
    infoGains:       { uA: 0.5, uB: 0.5,  uC: 0.5 },
    hasReasoningMap: { uA: true,  uB: true,  uC: true },
    hasEvidenceMap:  { uA: true,  uB: true,  uC: true },
    skwScores:       {},
    keywords:        [],
    ...overrides,
  };
}

// ── ① 群体停滞 ────────────────────────────────────────────────────────────────

describe('群体停滞', () => {
  it('全组静默均 > 30s → 触发 group_silence，targetUsers = 全组', () => {
    const result = baseResult({ silenceSeconds: { uA: 35, uB: 40, uC: 31 } });
    const triggers = runReasoningLayer(result, MEMBERS);
    const gs = triggers.filter((t) => t.type === 'group_silence');
    expect(gs).toHaveLength(1);
    expect(gs[0].targetUsers).toEqual(MEMBERS);
  });

  it('有人静默 < 30s → 不触发', () => {
    const result = baseResult({ silenceSeconds: { uA: 35, uB: 20, uC: 31 } });
    const triggers = runReasoningLayer(result, MEMBERS);
    expect(triggers.filter((t) => t.type === 'group_silence')).toHaveLength(0);
  });
});

// ── ② 个人停滞 ────────────────────────────────────────────────────────────────

describe('个人停滞', () => {
  it('某人发言比例 < 15% → 触发 low_participation，targetUsers = [该用户]', () => {
    const result = baseResult({ speakingRatios: { uA: 0.08, uB: 0.5, uC: 0.42 } });
    const triggers = runReasoningLayer(result, MEMBERS);
    const lp = triggers.filter((t) => t.type === 'low_participation');
    expect(lp).toHaveLength(1);
    expect(lp[0].userId).toBe('uA');
    expect(lp[0].targetUsers).toEqual(['uA']);
  });

  it('所有人比例 ≥ 15% → 不触发', () => {
    const result = baseResult({ speakingRatios: { uA: 0.15, uB: 0.5, uC: 0.35 } });
    const triggers = runReasoningLayer(result, MEMBERS);
    expect(triggers.filter((t) => t.type === 'low_participation')).toHaveLength(0);
  });
});

// ── ③ 阐述浅薄 ───────────────────────────────────────────────────────────────

describe('阐述浅薄', () => {
  it('条件A + 条件B 同时满足 → 触发 shallow_discussion', () => {
    // condA: srep > 0.65 AND infoGain < 0.3
    // condB: ttr < 0.4
    const result = baseResult({
      sreps:     { uA: 0.70, uB: 0.4, uC: 0.4 },
      infoGains: { uA: 0.20, uB: 0.5, uC: 0.5 },
      ttrs:      { uA: 0.35, uB: 0.6, uC: 0.6 },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    const sd = triggers.filter((t) => t.type === 'shallow_discussion');
    expect(sd).toHaveLength(1);
    expect(sd[0].userId).toBe('uA');
  });

  it('条件C + 条件B 同时满足 → 触发（argDensity < 0.02 且 LLM 两项都 false，加 TTR < 0.4）', () => {
    const result = baseResult({
      argDensities:    { uA: 0.01,  uB: 0.1,  uC: 0.1 },
      hasReasoningMap: { uA: false, uB: true,  uC: true },
      hasEvidenceMap:  { uA: false, uB: true,  uC: true },
      ttrs:            { uA: 0.35,  uB: 0.6,   uC: 0.6 },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    const sd = triggers.filter((t) => t.type === 'shallow_discussion');
    expect(sd).toHaveLength(1);
    expect(sd[0].userId).toBe('uA');
  });

  it('条件C 中 argDensity < 0.02 但 has_reasoning = true → 条件C 不成立，只有1条触发，不触发', () => {
    const result = baseResult({
      argDensities:    { uA: 0.01, uB: 0.1, uC: 0.1 },
      hasReasoningMap: { uA: true, uB: true, uC: true },  // has_reasoning = true，条件C 不成立
      hasEvidenceMap:  { uA: false, uB: true, uC: true },
      sreps:           { uA: 0.4,  uB: 0.4, uC: 0.4 },
      ttrs:            { uA: 0.6,  uB: 0.6, uC: 0.6 },   // 条件B 也不满足
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    expect(triggers.filter((t) => t.type === 'shallow_discussion')).toHaveLength(0);
  });

  it('只有1个条件异常 → 不触发', () => {
    const result = baseResult({
      ttrs: { uA: 0.35, uB: 0.6, uC: 0.6 },  // 只有条件B
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    expect(triggers.filter((t) => t.type === 'shallow_discussion')).toHaveLength(0);
  });
});

// ── ④ 信息缺口 ───────────────────────────────────────────────────────────────

describe('信息缺口', () => {
  it('存在关键词 skw pair 时，会生成 info_gap 触发并交给 LLM 后续评估目标用户', () => {
    const result = baseResult({
      keywords: ['资源'],
      skwScores: {
        资源: {
          uA: { uB: 0.75, uC: 0.20 },
          uB: { uA: 0.75, uC: 0.22 },
          uC: { uA: 0.20, uB: 0.22 },
        },
      },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    const ig = triggers.filter((t) => t.type === 'info_gap');
    expect(ig).toHaveLength(1);
    expect(ig[0].targetUsers).toEqual(MEMBERS);
    expect(ig[0].keyword).toBe('资源');
    expect(ig[0].skwScore).toBeCloseTo(0.2);
  });

  it('三人两两均 < 0.3 也会触发，最小 skw 会透传', () => {
    const result = baseResult({
      keywords: ['概念'],
      skwScores: {
        概念: {
          uA: { uB: 0.20, uC: 0.18 },
          uB: { uA: 0.20, uC: 0.25 },
          uC: { uA: 0.18, uB: 0.25 },
        },
      },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    const ig = triggers.filter((t) => t.type === 'info_gap');
    expect(ig).toHaveLength(1);
    expect(ig[0].targetUsers).toEqual(MEMBERS);
    expect(ig[0].skwScore).toBeCloseTo(0.18);
  });

  it('有 pair 落在旧模糊区间也仍会触发（由 LLM 最终裁决）', () => {
    const result = baseResult({
      keywords: ['信息'],
      skwScores: {
        信息: {
          uA: { uB: 0.45, uC: 0.20 },  // uA-uB 在模糊地带
          uB: { uA: 0.45, uC: 0.22 },
          uC: { uA: 0.20, uB: 0.22 },
        },
      },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    expect(triggers.filter((t) => t.type === 'info_gap')).toHaveLength(1);
  });

  it('所有 pair 均 > 0.6 也会进入 LLM 复核流程', () => {
    const result = baseResult({
      keywords: ['学习'],
      skwScores: {
        学习: {
          uA: { uB: 0.80, uC: 0.75 },
          uB: { uA: 0.80, uC: 0.70 },
          uC: { uA: 0.75, uB: 0.70 },
        },
      },
    });
    const triggers = runReasoningLayer(result, MEMBERS);
    const ig = triggers.filter((t) => t.type === 'info_gap');
    expect(ig).toHaveLength(1);
    expect(ig[0].skwScore).toBeCloseTo(0.7);
  });
});

// ── 全部正常，无触发 ──────────────────────────────────────────────────────────

describe('全部指标正常', () => {
  it('基线数据 → 无任何触发', () => {
    const triggers = runReasoningLayer(baseResult(), MEMBERS);
    expect(triggers).toHaveLength(0);
  });
});
