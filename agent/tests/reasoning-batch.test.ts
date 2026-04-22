import { computeHasReasoning } from '../src/skills/perception/reasoning';
import * as queries from '../src/db/queries';
import * as nlp from '../src/http/nlp-client';

jest.mock('../src/logger', () => ({
  createLogger: () => ({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

jest.mock('../src/db/queries');
jest.mock('../src/http/nlp-client');

const mockGetTranscriptsInWindow = queries.getTranscriptsInWindow as jest.MockedFunction<
  typeof queries.getTranscriptsInWindow
>;
const mockReasoningBatch = nlp.reasoningBatch as jest.MockedFunction<typeof nlp.reasoningBatch>;

describe('computeHasReasoning', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('整轮只发起一次批量论证结构判定，并按成员聚合文本', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([
      {
        transcript_id: 't1',
        session_id: 's1',
        group_id: 'g1',
        user_id: 'u1',
        speaker_name: '成员甲',
        text: '我建议先做 MVP，',
        start: new Date(),
        end: new Date(),
        duration: 2,
      } as never,
      {
        transcript_id: 't2',
        session_id: 's1',
        group_id: 'g1',
        user_id: 'u1',
        speaker_name: '成员甲',
        text: '因为这样范围更容易控制。',
        start: new Date(),
        end: new Date(),
        duration: 2,
      } as never,
      {
        transcript_id: 't3',
        session_id: 's1',
        group_id: 'g1',
        user_id: 'u2',
        speaker_name: '成员乙',
        text: '比如腾讯会议也用了类似做法。',
        start: new Date(),
        end: new Date(),
        duration: 3,
      } as never,
    ]);
    mockReasoningBatch.mockResolvedValue([
      {
        user_id: 'u1',
        reasoning_status: true,
        evidence_status: false,
        reasoning_source: '发言中明确说明了选择该方案的原因。',
        evidence_source: '发言中没有提供例子、数据或事实依据。',
      },
      {
        user_id: 'u2',
        reasoning_status: false,
        evidence_status: true,
        reasoning_source: '发言中只有观点表态，没有展开原因。',
        evidence_source: '发言中引用了具体案例作为支撑。',
      },
    ]);

    const result = await computeHasReasoning(
      's1',
      new Date('2026-04-22T10:00:00Z'),
      new Date('2026-04-22T10:01:00Z'),
      ['u1', 'u2', 'u3'],
    );

    expect(mockReasoningBatch).toHaveBeenCalledTimes(1);
    expect(mockReasoningBatch).toHaveBeenCalledWith([
      { user_id: 'u1', text: '我建议先做 MVP， 因为这样范围更容易控制。' },
      { user_id: 'u2', text: '比如腾讯会议也用了类似做法。' },
    ]);
    expect(result.hasReasoningMap).toEqual({ u1: true, u2: false, u3: null });
    expect(result.hasEvidenceMap).toEqual({ u1: false, u2: true, u3: null });
    expect(result.reasoningSourceMap.u1).toBe('发言中明确说明了选择该方案的原因。');
    expect(result.evidenceSourceMap.u2).toBe('发言中引用了具体案例作为支撑。');
  });

  it('全员无发言时不调用批量接口，并返回空结果映射', async () => {
    mockGetTranscriptsInWindow.mockResolvedValue([]);

    const result = await computeHasReasoning(
      's1',
      new Date('2026-04-22T10:00:00Z'),
      new Date('2026-04-22T10:01:00Z'),
      ['u1', 'u2'],
    );

    expect(mockReasoningBatch).not.toHaveBeenCalled();
    expect(result.hasReasoningMap).toEqual({ u1: null, u2: null });
    expect(result.hasEvidenceMap).toEqual({ u1: null, u2: null });
    expect(result.reasoningSourceMap).toEqual({ u1: null, u2: null });
    expect(result.evidenceSourceMap).toEqual({ u1: null, u2: null });
  });
});
