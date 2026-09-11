import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  className?: string
}

export default function Card({ children, className = '' }: Props) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${className}`}>{children}</section>
  )
}
