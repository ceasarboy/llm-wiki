function ensureUTC(dateStr: string): string {
  if (dateStr.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(dateStr)) {
    return dateStr
  }
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(dateStr)) {
    return dateStr + 'Z'
  }
  return dateStr
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    const date = new Date(ensureUTC(dateStr))
    if (isNaN(date.getTime())) return dateStr
    return date.toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return dateStr
  }
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    const date = new Date(ensureUTC(dateStr))
    if (isNaN(date.getTime())) return dateStr
    return date.toLocaleDateString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return dateStr
  }
}
