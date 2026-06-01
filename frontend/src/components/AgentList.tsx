import type { AgentInfo } from '../hooks/useWebSocket'
import { Avatar } from './Avatar'

interface Props {
  agents: AgentInfo[]
  connected: boolean
  myName: string
}

function timeSince(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

export function AgentList({ agents, connected, myName }: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="brand-pulse" />
          <span className="brand-name">MACP Multi-Agent Communication Platform</span>
        </div>
        <div className="sidebar-me">
          <span className={`status-dot ${connected ? 'on' : 'off'}`} />
          <span>管理人: {myName}</span>
        </div>
      </div>

      <div className="sidebar-label">Agents · {agents.length}</div>

      {agents.length === 0 && (
        <div className="sidebar-empty">waiting for agents…</div>
      )}

      {agents.map(a => (
        <div key={a.name} className="agent-card">
          <Avatar name={a.name} size={34} />
          <div className="agent-info">
            <div className="agent-name-row">
              <span className="agent-name">{a.name}</span>
              <span className="agent-hb">{timeSince(a.last_heartbeat)}</span>
            </div>
            <div className="agent-caps">
              {a.capabilities.map(c => (
                <span key={c} className="cap-tag">{c}</span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </aside>
  )
}
