interface Props {
  name: string
  size?: number
}

import { agentHue } from '../utils/color'
const hue = agentHue

function AgentIcon({ name, size }: { name: string; size: number }) {
  const s = Math.round(size * 0.52)
  const n = name.toLowerCase()

  if (n.includes('dba') || n.includes('db') || n.includes('database')) {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" fill="currentColor">
        <ellipse cx="8" cy="4" rx="5.5" ry="1.8" />
        <path d="M2.5 4v8c0 1 2.5 1.8 5.5 1.8s5.5-.8 5.5-1.8V4c0 1-2.5 1.8-5.5 1.8S2.5 5 2.5 4Z" />
        <ellipse cx="8" cy="8.5" rx="5.5" ry="1.5" />
      </svg>
    )
  }

  if (n.includes('k8s') || n.includes('kube') || n.includes('kubernetes')) {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <polygon points="8,1.5 13.5,4.7 13.5,11.3 8,14.5 2.5,11.3 2.5,4.7" />
        <circle cx="8" cy="8" r="1.5" fill="currentColor" />
        <line x1="8" y1="6.5" x2="8" y2="3.5" />
        <line x1="9.3" y1="7.2" x2="11.8" y2="5.8" />
        <line x1="9.3" y1="8.8" x2="11.8" y2="10.2" />
        <line x1="8" y1="9.5" x2="8" y2="12.5" />
        <line x1="6.7" y1="8.8" x2="4.2" y2="10.2" />
        <line x1="6.7" y1="7.2" x2="4.2" y2="5.8" />
      </svg>
    )
  }

  if (n.includes('network') || n.includes('net')) {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <circle cx="8" cy="8" r="1.5" fill="currentColor" />
        <circle cx="2.5" cy="4" r="1" fill="currentColor" />
        <circle cx="13.5" cy="4" r="1" fill="currentColor" />
        <circle cx="2.5" cy="12" r="1" fill="currentColor" />
        <circle cx="13.5" cy="12" r="1" fill="currentColor" />
        <line x1="3.5" y1="4.5" x2="6.8" y2="7" />
        <line x1="12.5" y1="4.5" x2="9.2" y2="7" />
        <line x1="3.5" y1="11.5" x2="6.8" y2="9" />
        <line x1="12.5" y1="11.5" x2="9.2" y2="9" />
      </svg>
    )
  }

  if (n.includes('claude') || n.includes('dev') || n.includes('code')) {
    return (
      <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="4,5 1.5,8 4,11" />
        <polyline points="12,5 14.5,8 12,11" />
        <line x1="9.5" y1="3" x2="6.5" y2="13" />
      </svg>
    )
  }

  // generic: CPU chip
  return (
    <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
      <rect x="4.5" y="4.5" width="7" height="7" rx="1" />
      <line x1="6" y1="4.5" x2="6" y2="2.5" /><line x1="8" y1="4.5" x2="8" y2="2.5" /><line x1="10" y1="4.5" x2="10" y2="2.5" />
      <line x1="6" y1="11.5" x2="6" y2="13.5" /><line x1="8" y1="11.5" x2="8" y2="13.5" /><line x1="10" y1="11.5" x2="10" y2="13.5" />
      <line x1="4.5" y1="6" x2="2.5" y2="6" /><line x1="4.5" y1="8" x2="2.5" y2="8" /><line x1="4.5" y1="10" x2="2.5" y2="10" />
      <line x1="11.5" y1="6" x2="13.5" y2="6" /><line x1="11.5" y1="8" x2="13.5" y2="8" /><line x1="11.5" y1="10" x2="13.5" y2="10" />
      <rect x="6.5" y="6.5" width="3" height="3" rx="0.5" fill="currentColor" fillOpacity="0.4" />
    </svg>
  )
}

function GearIcon({ size }: { size: number }) {
  const s = Math.round(size * 0.52)
  return (
    <svg width={s} height={s} viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 5a3 3 0 1 0 0 6A3 3 0 0 0 8 5Zm0 1.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z" />
      <path d="M9.2 1h-2.4l-.3 1.8a5.5 5.5 0 0 0-1.3.75L3.5 2.8 1.9 4.6l1.2 1.4a5.5 5.5 0 0 0-.35 1.5H1v2.4l1.7.3a5.5 5.5 0 0 0 .75 1.3L2.7 12.5l1.8 1.6 1.4-1.2a5.5 5.5 0 0 0 1.5.35V15h2.4l.3-1.7a5.5 5.5 0 0 0 1.3-.75l1.6.75 1.6-1.8-1.2-1.4a5.5 5.5 0 0 0 .35-1.5H15V6.2l-1.7-.3a5.5 5.5 0 0 0-.75-1.3l.75-1.6-1.8-1.6-1.4 1.2a5.5 5.5 0 0 0-1.5-.35L9.2 1Z" opacity="0.4" />
    </svg>
  )
}

export function Avatar({ name, size = 32 }: Props) {
  const isSystem = name === 'server' || name === 'orchestrator'
  const h = hue(name)
  const bg    = isSystem ? '#1a2233' : `hsl(${h},50%,14%)`
  const glow  = isSystem ? '#334155' : `hsl(${h},65%,45%)`
  const color = isSystem ? '#94a3b8' : `hsl(${h},80%,72%)`

  return (
    <div style={{ filter: `drop-shadow(0 0 5px ${glow}55)`, width: size, height: size, flexShrink: 0 }}>
      <div
        className="avatar"
        style={{ width: size, height: size, background: bg, color }}
      >
        {isSystem ? <GearIcon size={size} /> : <AgentIcon name={name} size={size} />}
      </div>
    </div>
  )
}
