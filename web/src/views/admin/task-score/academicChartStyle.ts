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

export function academicNiceMaximum(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const steps = [1, 1.25, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9, 10]
  return Number(((steps.find(step => normalized <= step) ?? 10) * magnitude).toPrecision(12))
}

export function academicTicks(maximum: number, targetIntervals = 5): number[] {
  if (!Number.isFinite(maximum) || maximum <= 0) return [0, 1]
  const magnitudeExponent = Math.floor(Math.log10(maximum))
  const candidates: Array<{ step: number, intervals: number }> = []
  for (let exponent = magnitudeExponent - 3; exponent <= magnitudeExponent + 1; exponent += 1) {
    for (const multiplier of [1, 2, 2.5, 5, 10]) {
      const step = multiplier * 10 ** exponent
      const rawIntervals = maximum / step
      const intervals = Math.round(rawIntervals)
      if (intervals >= 3 && intervals <= 10 && Math.abs(rawIntervals - intervals) < 1e-8) {
        candidates.push({ step, intervals })
      }
    }
  }
  candidates.sort((a, b) => Math.abs(a.intervals - targetIntervals) - Math.abs(b.intervals - targetIntervals))
  const selected = candidates[0]
  const intervalCount = selected?.intervals ?? Math.max(1, targetIntervals)
  const step = selected?.step ?? maximum / intervalCount
  return Array.from({ length: intervalCount + 1 }, (_, index) => Number((index * step).toPrecision(12)))
}
