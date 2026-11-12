import type { CSSProperties } from 'react'

const paths = {
  jobs: 'M8 3H4a1 1 0 0 0-1 1v4h5V3Zm13 0h-9v5h9V3ZM8 12H3v9h5v-9Zm13 0h-9v9h9v-9Z',
  workers: 'M8 8h8v8H8zM9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M6 5h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
  plus: 'M12 5v14M5 12h14',
  filter: 'M4 7h16M7 12h10M10 17h4M8 5v4m8 1v4m-4 1v4',
  sort: 'M8 4v16m-4-4 4 4 4-4m4-12h4m-4 5h3m-3 5h2',
  group: 'M3 4h18v4H3zM3 12h7v8H3zm11 0h7v8h-7z',
  chevron: 'm9 5 7 7-7 7',
  close: 'm6 6 12 12M6 18 18 6',
  refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2',
  logout: 'M9 5H5v14h4m5-14 7 7-7 7m-5-7h12',
  arrow: 'M5 12h14m-5-5 5 5-5 5',
} as const

export function Icon({ name, size = 18, style }: { name: keyof typeof paths; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0, ...style }}><path d={paths[name]} /></svg>
}
