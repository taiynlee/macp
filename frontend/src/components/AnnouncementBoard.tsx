import { useEffect, useRef } from 'react'
import type { AgentInfo, MACPMessage } from '../hooks/useWebSocket'
import { agentColors } from '../utils/color'

interface Props {
  messages: MACPMessage[]
  agents: AgentInfo[]
}

function formatTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  catch { return '' }
}

export function AnnouncementBoard({ messages, agents }: Props) {
  const alerts = messages.filter(m => m.type === 'alert' && m.priority === 'urgent')
  const scheduled = agents.filter(a => a.schedule && a.schedule.length > 0)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [alerts.length])

  const isEmpty = alerts.length === 0 && scheduled.length === 0

  return (
    <div className="board">
      <div className="board-header">
        <span className="board-title">Job 公告欄</span>
        {alerts.length > 0 && <span className="board-count">{alerts.length}</span>}
      </div>

      <div className="board-feed">
        {isEmpty && <div className="board-empty">— 尚無公告 —</div>}

        {scheduled.map(agent => {
          const c = agentColors(agent.name)
          return (
            <div key={agent.name} className="board-schedule" style={{ borderColor: c.border }}>
              <div className="board-schedule-header" style={{ background: c.header, borderBottomColor: c.border }}>
                <span className="board-schedule-agent" style={{ color: c.accent }}>{agent.name}</span>
                <span className="board-schedule-label">排程</span>
              </div>
              {agent.schedule.map(job => (
                <div key={job.name} className="board-job" style={{ borderBottomColor: c.border }}>
                  <code className="board-job-cron" style={{ color: c.text }}>{job.cron}</code>
                  <span className="board-job-desc">{job.desc}</span>
                  {job.last_success === true  && <span className="job-ok">✓</span>}
                  {job.last_success === false && <span className="job-fail">✗</span>}
                </div>
              ))}
            </div>
          )
        })}

        {alerts.map(msg => (
          <div key={msg.id} className="board-card">
            <div className="board-card-meta">
              <span className="board-card-sender">{msg.sender}</span>
              <span className="board-card-ts">{formatTime(msg.timestamp)}</span>
            </div>
            {msg.content && <div className="board-card-body">{msg.content}</div>}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
