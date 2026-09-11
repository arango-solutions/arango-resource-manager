/**
 * Uptime rendering. The seconds are computed server-side so sorting happens on
 * integers; this only formats them.
 */

export function formatUptime(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${seconds}s`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    const remainder = minutes % 60
    return remainder ? `${hours}h ${remainder}m` : `${hours}h`
  }

  const days = Math.floor(hours / 24)
  const remainder = hours % 24
  return remainder ? `${days}d ${remainder}h` : `${days}d`
}

/** A pod younger than ten minutes is a churn signal worth noticing. */
export function isYoung(seconds: number | null): boolean {
  return seconds !== null && seconds < 600
}

export function isRecent(isoTimestamp: string | null, withinSeconds = 3600): boolean {
  if (!isoTimestamp) return false
  const then = Date.parse(isoTimestamp)
  if (Number.isNaN(then)) return false
  return (Date.now() - then) / 1000 < withinSeconds
}
