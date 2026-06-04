import { useEffect, useRef } from 'react'
import type { AgentInfo, MACPMessage } from '../hooks/useWebSocket'
import { Avatar } from './Avatar'

import { agentColors, agentHue } from '../utils/color'

function senderStyle(name: string, light: boolean): React.CSSProperties {
  const c = agentColors(name, light)
  return { background: c.bg, borderColor: c.border, color: c.text, fontFamily: 'inherit' }
}

interface Props {
  messages: MACPMessage[]
  myName: string
  agents: AgentInfo[]
  onReply?: (sender: string) => void
  theme?: 'dark' | 'light'
}

function formatTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }
  catch { return '' }
}

// Detect psql / ASCII table output (lines with | or +--+ separators)
function looksLikeTable(text: string): boolean {
  const lines = text.split('\n').filter(l => l.trim())
  const tableLines = lines.filter(l => /[|+]/.test(l))
  return tableLines.length >= 2
}

function renderContent(content: string, forceCode = false) {
  if (forceCode || looksLikeTable(content)) {
    return <pre className="msg-pre">{content}</pre>
  }

  // Split on fenced code blocks
  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const code = part.slice(3, -3).replace(/^\n/, '')
          return <pre key={i} className="msg-pre">{code}</pre>
        }
        return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{part}</span>
      })}
    </>
  )
}

export function MessageFeed({ messages, myName, onReply, theme }: Props) {
  const isLight = theme === 'light'
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const feed = messages.filter(m =>
    m.type === 'discussion' ||
    m.type === 'report' ||
    m.type === 'alert' ||
    (m.type === 'system' && (m.action === 'agent_connected' || m.action === 'agent_disconnected'))
  )

  return (
    <div className="feed">
      {feed.length === 0 && (
        <div className="feed-empty">
          <div className="feed-empty-glyph">⬡</div>
          <div>No messages yet</div>
        </div>
      )}

      {feed.map(msg => {
        if (msg.type === 'system') {
          return (
            <div key={msg.id} className="sys-notice">
              <div className="sys-rule" />
              <span className="sys-text">
                {msg.action === 'agent_connected' ? `${msg.name} joined` : `${msg.name} left`}
              </span>
              <div className="sys-rule" />
            </div>
          )
        }

        if (msg.type === 'alert') {
          return (
            <div key={msg.id} className="alert-banner">
              <span className="alert-icon">⚡</span>
              <span className="alert-from">{msg.sender}</span>
              {msg.content && <span className="alert-text">{msg.content}</span>}
              <span className="ts">{formatTime(msg.timestamp)}</span>
            </div>
          )
        }

        const isMine = msg.sender === myName
        const isReport = msg.type === 'report'

        return (
          <div key={msg.id} className={`msg-row ${isMine ? 'mine' : 'other'}`}>
            {!isMine && <Avatar name={msg.sender} size={28} />}

            <div className="msg-col">
              {!isMine && (
                <div className="msg-meta">
                  <span className="msg-name" style={{ color: agentColors(msg.sender).accent }}>{msg.sender}</span>
                  <span className="ts">{formatTime(msg.timestamp)}</span>
                </div>
              )}
              {isMine && msg.target && msg.target !== 'all' && (
                <div className="msg-meta-mine">
                  <span className="msg-to-mine">→ @{msg.target}</span>
                </div>
              )}
              {msg.content && (
                <div className="bubble-wrap">
                  <div
                    className={`bubble ${isMine ? 'b-mine' : isReport ? 'b-report' : 'b-other'}`}
                    style={(!isMine && isReport) ? senderStyle(msg.sender, isLight) : undefined}
                  >
                    {renderContent(msg.content, isReport)}
                  </div>
                  {!isMine && onReply && (
                    <button
                      className="reply-btn"
                      title={`回覆 ${msg.sender}`}
                      onClick={() => onReply(msg.sender)}
                    >↩</button>
                  )}
                </div>
              )}
              {isMine && <div className="ts ts-right">{formatTime(msg.timestamp)}</div>}
            </div>
          </div>
        )
      })}

      <div ref={bottomRef} />
    </div>
  )
}
