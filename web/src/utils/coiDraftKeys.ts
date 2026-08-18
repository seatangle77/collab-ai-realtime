import type { CoiCoderRole } from '../api/admin/coi-units'

export function coiPreprocessDraftKey(sessionId: string): string {
  return `coi_preprocess_draft_${sessionId}`
}

export function coiUnitsDraftKey(sessionId: string): string {
  return `coi_units_draft_${sessionId}`
}

export function coiCodesDraftKey(sessionId: string, coderRole: CoiCoderRole): string {
  return `coi_codes_draft_${sessionId}_${coderRole}`
}

export function coiReviewStarsKey(sessionId: string, coderRole: CoiCoderRole): string {
  return `coi_review_stars_${sessionId}_${coderRole}`
}

export function legacyCoiCodingDraftKey(sessionId: string): string {
  return `coi_coding_draft_${sessionId}`
}

export function clearCoiDownstreamDrafts(sessionId: string): void {
  localStorage.removeItem(coiUnitsDraftKey(sessionId))
  localStorage.removeItem(coiCodesDraftKey(sessionId, 'coder_a'))
  localStorage.removeItem(coiCodesDraftKey(sessionId, 'coder_b'))
  localStorage.removeItem(coiCodesDraftKey(sessionId, 'final'))
  localStorage.removeItem(coiReviewStarsKey(sessionId, 'coder_a'))
  localStorage.removeItem(coiReviewStarsKey(sessionId, 'coder_b'))
  localStorage.removeItem(coiReviewStarsKey(sessionId, 'final'))
  localStorage.removeItem(legacyCoiCodingDraftKey(sessionId))
}
