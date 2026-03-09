export interface CsvColumn<T> {
  key: keyof T | string
  title: string
  format?: (row: T) => string
}

export interface ExportRowsToCsvOptions<T> {
  columns: CsvColumn<T>[]
  rows: T[]
  filename: string
}

function escapeCsvCell(raw: string): string {
  const needsQuote = /[",\n]/.test(raw)
  let value = raw.replace(/"/g, '""')
  if (needsQuote) {
    value = `"${value}"`
  }
  return value
}

export function exportRowsToCsv<T>(options: ExportRowsToCsvOptions<T>): void {
  const { columns, rows, filename } = options

  if (!columns.length) return
  if (!rows.length) return

  const header = columns.map((c) => escapeCsvCell(String(c.title ?? ''))).join(',')

  const lines: string[] = [header]

  for (const row of rows) {
    const cells = columns.map((col) => {
      let raw = ''
      if (col.format) {
        raw = col.format(row) ?? ''
      } else {
        const value = (row as any)[col.key as string]
        raw = value == null ? '' : String(value)
      }
      return escapeCsvCell(raw)
    })
    lines.push(cells.join(','))
  }

  const csvContent = lines.join('\n')
  const blob = new Blob(['\uFEFF', csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)

  const link = document.createElement('a')
  link.href = url
  link.download = filename || 'export.csv'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

