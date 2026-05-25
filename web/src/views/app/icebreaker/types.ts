export interface IcebreakerMember {
  id: string
  name: string
  initial: string
  bg: string
}

export interface IcebreakerGroup {
  id: string
  name: string
}

export interface AppCurrentGroup {
  id: string
  name: string
}

export interface ScoreImageStyle {
  gradient: string
  emoji: string
}

export interface ScoreDraft {
  value: number
  comment: string
  mvpTitle: string
  mvpReason: string
  imageStyle: ScoreImageStyle
}
