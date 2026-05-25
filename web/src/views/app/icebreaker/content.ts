import type { ScoreDraft, ScoreImageStyle } from './types'

export const P1_QUESTIONS_PER_MEMBER = 3
export const STORY_ROUNDS = 2

export const P1_FIXED = '先介绍一下自己——你叫什么名字？你的星座是什么？MBTI 是什么？（不知道 MBTI 的话，说说你觉得自己偏内向还是外向？）'

export const P1_EXTRA_POOL = [
  '用一道菜来形容你自己——你是什么菜？为什么？',
  '你有没有一个吃东西的奇怪口味偏好，说出来别人都觉得你怪？',
  '你有没有一个"连自己都觉得很蠢但就是改不掉"的习惯？',
  '你在朋友群里通常是什么角色——发疯的、拉架的、还是潜水的？',
  '你最近发呆的时候在想什么？',
  '你最近有没有做过一件事，做完之后在心里默默给自己鼓掌的？',
  '朋友最常拿你开玩笑的点是什么？',
  '你有没有一个"理论上该戒掉但完全没打算戒"的坏习惯？',
  '你上一次骗自己"就最后一次"是什么事？',
  '你有没有一件"只要没人看见就不算"的事？',
  '你最近做过最"不像自己"的一件事是什么？',
  '你有没有一首歌，单曲循环次数自己都不敢数？',
  '你有没有一个"只有你自己觉得好笑、但给别人解释半天他们也不懂"的梗？',
  '你睡前胡思乱想的时候通常在想什么？',
  '你最容易"破防"的点是什么——什么事会让你突然绷不住？',
  '你在家一个人的时候，会做什么在外面绝对不做的事？',
  '你有没有一件事，"明明知道在浪费时间，但就是停不下来"？',
  '你上一次在公共场合尴尬到想消失是什么时候？',
  '你有没有一个偷偷坚持的小迷信或仪式感？',
  '如果给你现在的状态配一首 BGM，你会选什么歌？',
  '如果你是一种天气，你今天是什么天气？',
  '你有没有一件"明明不该笑但还是笑出来了"的事？',
  '你最近搜索过的最奇怪的一个问题是什么？',
  '你有没有一个"偷偷挺厉害但很少告诉别人"的技能？',
]

export const STORY_POOL = [
  '一个快递员在送一封没有地址的包裹，上面只写着"给最需要它的人"……',
  '深夜 12 点，手机突然收到一条陌生消息："我知道你今天做了什么。"……',
  '便利店收银台上，你发现了一张字条：如果你捡到这张纸，请不要回头……',
  '早上醒来，你发现镜子里的自己比你早了整整三秒……',
  '电梯门打开，里面站着的人和你长得一模一样，而且正在按同一层楼……',
  '一只流浪猫突然开口说了一句话，然后就再也不说了……',
  '博物馆镇馆之宝今天早上不翼而飞，监控只拍到它自己走出了大门……',
  '不知从何时起，城里所有人都忘记了"蓝色"这种颜色……',
  '废弃游乐场里，一架旋转木马在没有风的深夜自己转了起来……',
  '旧书店里有一本日记，翻开来，上面写的竟然是你明年 365 天的每一天……',
  '全市所有时钟在同一秒停了下来，指针停在了 3:33……',
  '邮差送来一封信，收件人是「二十年后的你」，寄件人是「现在的你」……',
]

export const SCORE_COMMENTS = [
  '离谱，但居然接住了。',
  '剧情很野，逻辑先下班了。',
  '像临时起意，但气氛是有的。',
  '圆得有点辛苦，不过没崩。',
  '前半段悬疑，后半段随缘。',
  '很难评，但确实挺好笑。',
  '故事不一定合理，但你们很敢编。',
  '这走向没人猜到，包括你们自己。',
  '有点乱，但乱得挺有生命力。',
  '合理性先不说，节目效果到了。',
]

export const SCORE_MVP_TITLES = [
  '全场最会圆奖',
  '剧情急救员',
  '硬接大师',
  '反转制造机',
  '气氛续命王',
  '临场补设定大师',
]

export const SCORE_MVP_REASONS = [
  '别人还在懵，你已经开始补设定了。',
  '一句话把快散架的剧情扶住了。',
  '虽然方向很怪，但至少有方向。',
  '成功让故事从尴尬变成了好笑。',
  '你这一接，大家突然又有话编了。',
  '硬是把没路的剧情接出了一条路。',
]

export const SCORE_IMAGE_STYLES: ScoreImageStyle[] = [
  { gradient: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4c1d95 100%)', emoji: '🌌' },
  { gradient: 'linear-gradient(135deg, #064e3b 0%, #065f46 50%, #047857 100%)', emoji: '🌿' },
  { gradient: 'linear-gradient(135deg, #7f1d1d 0%, #991b1b 50%, #b91c1c 100%)', emoji: '🔮' },
  { gradient: 'linear-gradient(135deg, #0c4a6e 0%, #075985 50%, #0369a1 100%)', emoji: '🌊' },
  { gradient: 'linear-gradient(135deg, #451a03 0%, #78350f 50%, #92400e 100%)', emoji: '🏜️' },
  { gradient: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)', emoji: '🤖' },
]

export function shuffle<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const tmp = a[i] as T
    a[i] = a[j] as T
    a[j] = tmp
  }
  return a
}

export function buildP1MemberQuestions(memberCount: number): string[][] {
  return Array.from({ length: memberCount }, () => [P1_FIXED, ...shuffle(P1_EXTRA_POOL).slice(0, 2)])
}

export function pickStoryOpening(): string {
  return shuffle(STORY_POOL)[0]!
}

export function createScoreDraft(): ScoreDraft {
  return {
    value: Math.floor(Math.random() * 26) + 65,
    comment: SCORE_COMMENTS[Math.floor(Math.random() * SCORE_COMMENTS.length)]!,
    mvpTitle: SCORE_MVP_TITLES[Math.floor(Math.random() * SCORE_MVP_TITLES.length)]!,
    mvpReason: SCORE_MVP_REASONS[Math.floor(Math.random() * SCORE_MVP_REASONS.length)]!,
    imageStyle: SCORE_IMAGE_STYLES[Math.floor(Math.random() * SCORE_IMAGE_STYLES.length)]!,
  }
}
