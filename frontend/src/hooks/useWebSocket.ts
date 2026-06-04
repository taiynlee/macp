import { useCallback, useEffect, useRef, useState } from 'react'

export interface MACPMessage {
  id: string
  timestamp: string
  sender: string
  target?: string
  type: 'task' | 'report' | 'discussion' | 'alert' | 'system'
  action?: string
  content?: string
  priority?: 'low' | 'normal' | 'high' | 'urgent'
  name?: string          // for system agent_connected / agent_disconnected
  [key: string]: unknown
}

export interface CronJob {
  name: string
  cron: string
  desc: string
  last_success?: boolean
}

export interface AgentInfo {
  name: string
  capabilities: string[]
  connected_at: string
  last_heartbeat: string
  schedule: CronJob[]
}

interface UseWebSocketReturn {
  messages: MACPMessage[]
  agents: AgentInfo[]
  connected: boolean
  connect: (name: string) => void
  disconnect: () => void
  send: (payload: Partial<MACPMessage>) => void
}

const SERVER = import.meta.env.VITE_SERVER_URL ?? ''   // '' = same origin via vite proxy

async function fetchAgents(): Promise<AgentInfo[]> {
  try {
    const res = await fetch(`${SERVER}/api/agents`)
    return res.ok ? res.json() : []
  } catch {
    return []
  }
}

export function useWebSocket(): UseWebSocketReturn {
  const [messages, setMessages] = useState<MACPMessage[]>([])
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const nameRef = useRef<string>('user')

  const refreshAgents = useCallback(() => {
    fetchAgents().then(setAgents)
  }, [])

  const send = useCallback((payload: Partial<MACPMessage>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      sender: nameRef.current,
      ...payload,
    }))
  }, [])

  const connect = useCallback((name: string) => {
    if (wsRef.current) wsRef.current.close()
    nameRef.current = name

    const url = `${SERVER.replace(/^http/, 'ws')}/ws?name=${encodeURIComponent(name)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      refreshAgents()
    }

    ws.onmessage = (ev) => {
      try {
        const msg: MACPMessage = JSON.parse(ev.data)
        const action = msg.action

        if (msg.type === 'system' && (action === 'agent_connected' || action === 'agent_disconnected' || action === 'schedule_updated' || action === 'capabilities_updated')) {
          refreshAgents()
        }

        // always append to feed (except pure heartbeat acks)
        if (!(msg.type === 'system' && action === 'registered')) {
          setMessages(prev => [...prev.slice(-499), msg])
        }
      } catch {
        // ignore malformed
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
    }
  }, [refreshAgents])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
  }, [])

  useEffect(() => () => { wsRef.current?.close() }, [])

  // poll every 10s to catch any missed schedule_updated events during long discovery
  useEffect(() => {
    if (!connected) return
    const id = setInterval(refreshAgents, 10_000)
    return () => clearInterval(id)
  }, [connected, refreshAgents])

  return { messages, agents, connected, connect, disconnect, send }
}
