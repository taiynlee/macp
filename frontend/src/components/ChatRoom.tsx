import { useRef, useState, useMemo, useCallback, useEffect } from 'react'
import type { AgentInfo, MACPMessage } from '../hooks/useWebSocket'
import { AgentList } from './AgentList'
import { MessageFeed } from './MessageFeed'
import { AnnouncementBoard } from './AnnouncementBoard'
import { Avatar } from './Avatar'

interface Props {
  messages: MACPMessage[]
  agents: AgentInfo[]
  connected: boolean
  myName: string
  onSend: (payload: Partial<MACPMessage>) => void
  onDisconnect: () => void
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}

function useResizable(key: string, initial: number, min: number, max: number, invert = false) {
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem(key)
    return saved ? Number(saved) : initial
  })
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = width
    const onMove = (ev: MouseEvent) => {
      const delta = invert ? startX - ev.clientX : ev.clientX - startX
      const next = Math.max(min, Math.min(max, startW + delta))
      setWidth(next)
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [width, min, max, invert])
  useEffect(() => { localStorage.setItem(key, String(width)) }, [key, width])
  return { width, onMouseDown }
}

function parseTarget(text: string): { target: string; content: string } {
  const m = text.match(/^@(\S+)\s+([\s\S]+)$/)
  if (m) return { target: m[1], content: m[2].trim() }
  return { target: 'all', content: text.trim() }
}

const SpeechRecognition = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition

export function ChatRoom({ messages, agents, connected, myName, onSend, onDisconnect, theme, onToggleTheme }: Props) {
  const left  = useResizable('panel-left',  230, 160, 400)
  const right = useResizable('panel-right', 260, 180, 480, true)
  const [text, setText] = useState('')
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<any>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const historyRef = useRef<string[]>([])
  const historyIdx = useRef<number>(-1)

  const targetHint = useMemo(() => {
    const m = text.match(/^@(\S+)/)
    return m ? m[1] : 'all'
  }, [text])

  const mentionQuery = useMemo(() => {
    if (!dropdownOpen) return null
    const m = text.match(/@(\S*)$/)
    return m ? m[1] : null
  }, [text, dropdownOpen])

  const mentionOptions = useMemo(() => {
    if (mentionQuery === null) return []
    const opts = ['all', ...agents.map(a => a.name)]
    const q = mentionQuery.toLowerCase()
    return q ? opts.filter(n => n.toLowerCase().startsWith(q)) : opts
  }, [agents, mentionQuery])

  function autoResize() {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }

  function handleChange(val: string) {
    setText(val)
    setDropdownOpen(/@\S*$/.test(val))
    requestAnimationFrame(autoResize)
  }

  function pickMention(name: string) {
    setText(text.replace(/@\S*$/, `@${name} `))
    setDropdownOpen(false)
    inputRef.current?.focus()
  }

  function handleReply(sender: string) {
    setText(`@${sender} `)
    historyIdx.current = -1
    inputRef.current?.focus()
  }

  function handleSend() {
    const raw = text.trim()
    if (!raw) return
    const { target, content } = parseTarget(raw)
    if (!content) return
    onSend({ type: 'discussion', target, content })
    historyRef.current = [raw, ...historyRef.current.slice(0, 99)]
    historyIdx.current = -1
    setText('')
    setDropdownOpen(false)
    requestAnimationFrame(() => {
      if (inputRef.current) inputRef.current.style.height = 'auto'
    })
    inputRef.current?.focus()
  }

  function toggleVoice() {
    if (!SpeechRecognition) {
      alert('此瀏覽器不支援語音輸入，請使用 Chrome 或 Edge。')
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      recognitionRef.current = null
      setListening(false)
      inputRef.current?.focus()
      return
    }
    const rec = new SpeechRecognition()
    rec.lang = 'zh-TW'
    rec.interimResults = false  // only final results → no flickering
    rec.continuous = true       // keep recording until user stops
    rec.onresult = (e: any) => {
      const transcript = Array.from(e.results)
        .filter((r: any) => r.isFinal)
        .map((r: any) => r[0].transcript)
        .join('')
      if (transcript) {
        setText(prev => prev + transcript)
        requestAnimationFrame(autoResize)
      }
    }
    rec.onend = () => {
      setListening(false)
      recognitionRef.current = null
    }
    rec.onerror = (e: any) => {
      if (e.error !== 'aborted') console.warn('speech error:', e.error)
      setListening(false)
      recognitionRef.current = null
    }
    rec.start()
    recognitionRef.current = rec
    setListening(true)
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape') { setDropdownOpen(false); return }
    if (e.key === 'Enter' && !e.shiftKey && !dropdownOpen) {
      e.preventDefault()
      handleSend()
      return
    }
    if (e.key === 'ArrowUp' && !dropdownOpen) {
      e.preventDefault()
      const h = historyRef.current
      if (!h.length) return
      const next = Math.min(historyIdx.current + 1, h.length - 1)
      historyIdx.current = next
      setText(h[next])
      return
    }
    if (e.key === 'ArrowDown' && !dropdownOpen) {
      e.preventDefault()
      const next = historyIdx.current - 1
      if (next < 0) {
        historyIdx.current = -1
        setText('')
      } else {
        historyIdx.current = next
        setText(historyRef.current[next])
      }
    }
  }

  return (
    <div className="layout">
      <AgentList agents={agents} connected={connected} myName={myName} style={{ width: left.width }} />
      <div className="resizer" onMouseDown={left.onMouseDown} />

      <div className="chat-panel">
        <div className="topbar">
          <span className="topbar-channel">Agent 協作平台</span>
          <button className="btn-theme" onClick={onToggleTheme} title="切換主題">
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
          <button className="btn-power" onClick={onDisconnect} title="disconnect">⏻</button>
        </div>

        <MessageFeed messages={messages} myName={myName} agents={agents} onReply={handleReply} theme={theme} />

        <div className="composer">
          {dropdownOpen && mentionOptions.length > 0 && (
            <div className="mention-list">
              {mentionOptions.map(name => (
                <div key={name} className="mention-item" onMouseDown={() => pickMention(name)}>
                  <Avatar name={name} size={20} />
                  <span>{name}</span>
                </div>
              ))}
            </div>
          )}
          <div className="composer-box">
            <span className="target-tag">@{targetHint}</span>
            <textarea
              ref={inputRef}
              className="composer-input"
              value={text}
              rows={1}
              onChange={e => handleChange(e.target.value)}
              onKeyDown={handleKey}
              onBlur={() => setTimeout(() => setDropdownOpen(false), 120)}
              placeholder="傳訊息… 或 @ 選擇對象"
              autoComplete="off"
              autoFocus
            />
            {SpeechRecognition && (
              <button
                className={`btn-mic ${listening ? 'btn-mic--on' : ''}`}
                onClick={toggleVoice}
                title={listening ? '停止錄音' : '語音輸入'}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 1a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm-1 17.93A8 8 0 0 1 4 11H2a10 10 0 0 0 9 9.93V23h2v-2.07A10 10 0 0 0 22 11h-2a8 8 0 0 1-7 7.93z"/>
                </svg>
              </button>
            )}
            <button className="btn-send" onClick={handleSend}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div className="resizer" onMouseDown={right.onMouseDown} />
      <AnnouncementBoard messages={messages} agents={agents} style={{ width: right.width }} />
    </div>
  )
}
