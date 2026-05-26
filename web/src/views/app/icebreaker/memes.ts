import type { ScoreMeme } from './types'

export const ICEBREAKER_MEMES: ScoreMeme[] = [
  {
    id: 'laughing-chaos',
    label: '笑到离场',
    mood: '爆笑',
    imageUrl: 'https://media.giphy.com/media/10JhviFuU2gWD6/giphy.gif',
    fallbackEmoji: '🤣',
    keywords: ['好笑', '爆笑', '节目效果', '精彩', '敢编'],
  },
  {
    id: 'surprised-pikachu',
    label: '怎么会这样',
    mood: '震惊',
    imageUrl: 'https://media.giphy.com/media/6nWhy3ulBL7GSCvKw6/giphy.gif',
    fallbackEmoji: '😳',
    keywords: ['震惊', '反转', '没人猜到', '突然', '离谱'],
  },
  {
    id: 'confused-math',
    label: '脑子在加载',
    mood: '迷惑',
    imageUrl: 'https://media.giphy.com/media/l3q2K5jinAlChoCLS/giphy.gif',
    fallbackEmoji: '🤔',
    keywords: ['逻辑', '难评', '看不懂', '很难评', '懵'],
  },
  {
    id: 'this-is-fine',
    label: '先假装没事',
    mood: '故事崩坏',
    imageUrl: 'https://media.giphy.com/media/QMHoU66sBXqqLqYvGO/giphy.gif',
    fallbackEmoji: '🙂',
    keywords: ['崩', '散架', '急救', '圆', '辛苦'],
  },
  {
    id: 'typing-fast',
    label: '疯狂补设定',
    mood: '硬接',
    imageUrl: 'https://media.giphy.com/media/ule4vhcY1xEKQ/giphy.gif',
    fallbackEmoji: '⌨️',
    keywords: ['补设定', '硬接', '接住', '续命', '圆奖'],
  },
  {
    id: 'mind-blown',
    label: '大脑重启',
    mood: '抽象',
    imageUrl: 'https://media.giphy.com/media/Um3ljJl8jrnHy/giphy.gif',
    fallbackEmoji: '🤯',
    keywords: ['抽象', '很野', '发疯', '怪', '走向'],
  },
  {
    id: 'side-eye',
    label: '你认真的吗',
    mood: '尴尬',
    imageUrl: 'https://media.giphy.com/media/H5C8CevNMbpBqNqFjl/giphy.gif',
    fallbackEmoji: '😐',
    keywords: ['尴尬', '沉默', '短', '没有', '随缘'],
  },
  {
    id: 'chef-kiss',
    label: '有点东西',
    mood: '高光',
    imageUrl: 'https://media.giphy.com/media/LOcPt9gfuNOSI/giphy.gif',
    fallbackEmoji: '👌',
    keywords: ['厉害', '最佳', '称号', '大师', '制造机'],
  },
  {
    id: 'applause',
    label: '队友太强',
    mood: '夸夸',
    imageUrl: 'https://media.giphy.com/media/nbvFVPiEiJH6JOGIok/giphy.gif',
    fallbackEmoji: '👏',
    keywords: ['强', 'MVP', '全场', '得奖', '扶住'],
  },
  {
    id: 'dramatic-exit',
    label: '剧情下班',
    mood: '离谱',
    imageUrl: 'https://media.giphy.com/media/3o7TKqnN349PBUtGFO/giphy.gif',
    fallbackEmoji: '🚪',
    keywords: ['下班', '乱', '生命力', '不合理', '离场'],
  },
]

export function pickIcebreakerMeme(input: {
  score: number
  comment: string
  mvpTitle: string
  mvpReason: string
  story: string
}): ScoreMeme {
  const haystack = [
    input.comment,
    input.mvpTitle,
    input.mvpReason,
    input.story,
  ].join(' ')

  const matched = ICEBREAKER_MEMES.find((meme) =>
    meme.keywords.some((keyword) => haystack.includes(keyword)),
  )
  if (matched) return matched

  if (input.story.trim().length < 18 || input.score < 60) {
    return ICEBREAKER_MEMES.find((meme) => meme.id === 'side-eye')!
  }
  if (input.score >= 88) {
    return ICEBREAKER_MEMES.find((meme) => meme.id === 'applause')!
  }
  if (input.score >= 78) {
    return ICEBREAKER_MEMES.find((meme) => meme.id === 'laughing-chaos')!
  }

  const index = Math.abs(input.comment.length + input.mvpTitle.length + input.story.length) % ICEBREAKER_MEMES.length
  return ICEBREAKER_MEMES[index]!
}
