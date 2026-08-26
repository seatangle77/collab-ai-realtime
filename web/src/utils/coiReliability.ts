import type { CoiCategory } from '../api/admin/coi-units'

export const COI_RELIABILITY_CATEGORIES: CoiCategory[] = ['TE', 'EX', 'IN', 'RE', 'OTHER']

export interface CoiReliabilityInput {
  unitId: string
  sessionId: string
  sessionTitle: string
  orderIndex: number
  content: string
  coderA: CoiCategory[]
  coderC: CoiCategory[]
}

export interface CoiReliabilityPair extends CoiReliabilityInput {
  categoryA: CoiCategory
  categoryC: CoiCategory
  agreed: boolean
}

export interface CoiReliabilityResult {
  totalCount: number
  eligibleCount: number
  missingCount: number
  invalidMultiCount: number
  agreedCount: number
  disagreementCount: number
  observedAgreement: number | null
  expectedAgreement: number | null
  cohenKappa: number | null
  pairs: CoiReliabilityPair[]
  disagreements: CoiReliabilityPair[]
  confusionMatrix: Record<CoiCategory, Record<CoiCategory, number>>
}

function emptyMatrix(): Record<CoiCategory, Record<CoiCategory, number>> {
  return Object.fromEntries(
    COI_RELIABILITY_CATEGORIES.map(row => [
      row,
      Object.fromEntries(COI_RELIABILITY_CATEGORIES.map(column => [column, 0])),
    ]),
  ) as Record<CoiCategory, Record<CoiCategory, number>>
}

export function calculateCoiReliability(inputs: CoiReliabilityInput[]): CoiReliabilityResult {
  const invalidMultiCount = inputs.filter(item => item.coderA.length > 1 || item.coderC.length > 1).length
  const missingCount = inputs.filter(item =>
    item.coderA.length <= 1
    && item.coderC.length <= 1
    && (item.coderA.length === 0 || item.coderC.length === 0),
  ).length
  const pairs: CoiReliabilityPair[] = inputs
    .filter(item => item.coderA.length === 1 && item.coderC.length === 1)
    .map(item => ({
      ...item,
      categoryA: item.coderA[0]!,
      categoryC: item.coderC[0]!,
      agreed: item.coderA[0] === item.coderC[0],
    }))

  const confusionMatrix = emptyMatrix()
  const countA = Object.fromEntries(COI_RELIABILITY_CATEGORIES.map(category => [category, 0])) as Record<CoiCategory, number>
  const countC = Object.fromEntries(COI_RELIABILITY_CATEGORIES.map(category => [category, 0])) as Record<CoiCategory, number>
  for (const pair of pairs) {
    confusionMatrix[pair.categoryA][pair.categoryC] += 1
    countA[pair.categoryA] += 1
    countC[pair.categoryC] += 1
  }

  const eligibleCount = pairs.length
  const agreedCount = pairs.filter(pair => pair.agreed).length
  const observedAgreement = eligibleCount > 0 ? agreedCount / eligibleCount : null
  const expectedAgreement = eligibleCount > 0
    ? COI_RELIABILITY_CATEGORIES.reduce(
      (sum, category) => sum + (countA[category] / eligibleCount) * (countC[category] / eligibleCount),
      0,
    )
    : null
  const denominator = expectedAgreement === null ? null : 1 - expectedAgreement
  const cohenKappa = observedAgreement === null || denominator === null || Math.abs(denominator) < 1e-12
    ? null
    : (observedAgreement - expectedAgreement!) / denominator

  return {
    totalCount: inputs.length,
    eligibleCount,
    missingCount,
    invalidMultiCount,
    agreedCount,
    disagreementCount: eligibleCount - agreedCount,
    observedAgreement,
    expectedAgreement,
    cohenKappa,
    pairs,
    disagreements: pairs.filter(pair => !pair.agreed),
    confusionMatrix,
  }
}
