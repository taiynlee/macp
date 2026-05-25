import { useState } from 'react'
import { ChatRoom } from './components/ChatRoom'
import { useWebSocket } from './hooks/useWebSocket'

export function App() {
  const { messages, agents, connected, connect, disconnect, send } = useWebSocket()
  const [nameInput, setNameInput] = useState('')
  const [myName, setMyName] = useState('')

  function handleConnect() {
    const name = nameInput.trim() || 'operator'
    setMyName(name)
    connect(name)
  }

  if (!connected) {
    return (
      <div className="connect-screen">
        <div className="connect-box">
          <div className="connect-logo">
            <div className="connect-icon">🤖</div>
            <div className="connect-title"><span>MACP</span></div>
          </div>
          <div className="connect-sub">Multi-Agents Communication Platform</div>
          <input
            className="connect-input"
            placeholder="your name (e.g. operator)"
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleConnect()}
            autoFocus
          />
          <button className="btn-connect" onClick={handleConnect}>connect</button>
        </div>
      </div>
    )
  }

  return (
    <ChatRoom
      messages={messages}
      agents={agents}
      connected={connected}
      myName={myName}
      onSend={send}
      onDisconnect={disconnect}
    />
  )
}
