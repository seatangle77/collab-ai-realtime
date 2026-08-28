export const ACADEMIC_CONDITION_COLORS: Record<string, string> = {
  no_assistance: '#4B5563',
  glasses: '#0072B2',
  app_notification: '#D55E00',
}

export const ACADEMIC_CONDITION_LABELS: Record<string, string> = {
  no_assistance: 'No Assistance',
  glasses: 'Smart Glasses',
  app_notification: 'App Notification',
}

export function academicConditionColor(condition: string): string {
  return ACADEMIC_CONDITION_COLORS[condition] ?? '#4B5563'
}

export function academicConditionLabel(condition: string): string {
  return ACADEMIC_CONDITION_LABELS[condition] ?? condition
}

export function academicPValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'p = —'
  if (value < 0.001) return 'p < .001'
  return `p = ${value.toFixed(3).replace(/^0/, '')}`
}

export function academicNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}
