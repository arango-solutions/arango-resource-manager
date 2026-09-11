/** Rendering of resource quantities. `null` means unset, and shows as an em dash. */

export function formatCpu(cores: number | null): string {
  if (cores === null) return '—'
  if (cores === 0) return '0'
  if (cores < 1) return `${Math.round(cores * 1000)}m`
  return String(Number(cores.toFixed(2)))
}

const UNITS: [string, number][] = [
  ['Ei', 1024 ** 6],
  ['Pi', 1024 ** 5],
  ['Ti', 1024 ** 4],
  ['Gi', 1024 ** 3],
  ['Mi', 1024 ** 2],
  ['Ki', 1024],
]

export function formatMemory(bytes: number | null): string {
  if (bytes === null) return '—'
  for (const [suffix, factor] of UNITS) {
    if (bytes >= factor) return `${Number((bytes / factor).toFixed(1))}${suffix}`
  }
  return `${bytes}B`
}

export function formatPercent(ratio: number | null): string {
  if (ratio === null) return '—'
  if (ratio > 0 && ratio < 0.001) return '<0.1%'
  return `${Number((ratio * 100).toFixed(1))}%`
}

/** Usage against what was reserved. Null when either side is unknown. */
export function efficiency(used: number | null, reserved: number | null): number | null {
  if (used === null || !reserved) return null
  return used / reserved
}
