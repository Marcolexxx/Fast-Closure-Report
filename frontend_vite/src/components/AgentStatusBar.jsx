/**
 * AgentStatusBar — PRD §4.3 全局 Agent 状态胶囊
 * 
 * 功能：
 * - 通过 WebSocket 订阅当前任务状态（IDLE/RUNNING/WAITING_HUMAN）
 * - 状态变化时显示顶部彩色条 + 胶囊 overlay
 * - WAITING_HUMAN 时脉冲动画 + 快捷跳转 HIL 提交界面
 * - 30s PING/PONG heartbeat（已在 api.js connectTaskWs 中实现）
 * - 组件卸载时自动关闭 WS 连接
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { connectTaskWs } from '../api'

const STATUS_CONFIG = {
  IDLE: {
    label: 'Agent 空闲',
    color: 'var(--color-border)',
    bg: 'rgba(255,255,255,0.04)',
    pulse: false,
  },
  RUNNING: {
    label: 'Agent 运行中',
    color: 'var(--color-primary)',
    bg: 'rgba(var(--color-primary-rgb, 124,110,245),0.12)',
    pulse: false,
  },
  WAITING_HUMAN: {
    label: '⚡ 等待您操作',
    color: 'var(--color-warn, #f5a623)',
    bg: 'rgba(245,166,35,0.12)',
    pulse: true,
  },
  ERROR: {
    label: '任务错误',
    color: 'var(--color-danger)',
    bg: 'rgba(255,59,48,0.12)',
    pulse: false,
  },
}

export default function AgentStatusBar({ taskId }) {
  const [status, setStatus] = useState(taskId ? 'RUNNING' : 'IDLE')
  const [lastStep, setLastStep] = useState('')
  const [visible, setVisible] = useState(!!taskId)
  const wsRef = useRef(null)
  const navigate = useNavigate()

  const handleMessage = useCallback((msg) => {
    if (!msg) return
    const newStatus = msg.status || msg.type?.toUpperCase()
    if (newStatus && STATUS_CONFIG[newStatus]) {
      setStatus(newStatus)
    }
    if (msg.step_desc) setLastStep(msg.step_desc)
    if (msg.type === 'pong') return  // heartbeat reply, ignore
  }, [])

  useEffect(() => {
    if (!taskId) {
      setStatus('IDLE')
      setVisible(false)
      return
    }
    setVisible(true)
    // Connect WebSocket
    wsRef.current = connectTaskWs(taskId, handleMessage)
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [taskId, handleMessage])

  if (!visible) return null

  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.IDLE

  return (
    <>
      {/* Top progress strip */}
      <div
        id="agent-status-strip"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: cfg.color,
          zIndex: 9999,
          transition: 'background 0.4s',
          ...(cfg.pulse ? {
            animation: 'agent-pulse-strip 1.5s ease-in-out infinite alternate',
          } : {}),
        }}
      />
      {/* Capsule badge */}
      <div
        id="agent-status-capsule"
        style={{
          position: 'fixed',
          top: 16,
          right: 24,
          zIndex: 9998,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 14px',
          borderRadius: 24,
          background: cfg.bg,
          border: `1px solid ${cfg.color}`,
          backdropFilter: 'blur(12px)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.25)',
          cursor: status === 'WAITING_HUMAN' ? 'pointer' : 'default',
          transition: 'all 0.3s cubic-bezier(0.34,1.56,0.64,1)',
          ...(cfg.pulse ? {
            animation: 'agent-pulse-capsule 1.5s ease-in-out infinite alternate',
          } : {}),
        }}
        onClick={() => {
          if (status === 'WAITING_HUMAN' && taskId) {
            navigate(`/tasks/${taskId}`)
          }
        }}
        title={status === 'WAITING_HUMAN' ? '点击进入 HIL 确认界面' : ''}
      >
        {/* Status dot */}
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: cfg.color,
            display: 'inline-block',
            flexShrink: 0,
            ...(cfg.pulse ? {
              animation: 'agent-dot-pulse 1.2s ease-in-out infinite',
            } : {}),
          }}
        />
        <span style={{ fontSize: 12, fontWeight: 600, color: cfg.color, whiteSpace: 'nowrap' }}>
          {cfg.label}
        </span>
        {lastStep && (
          <span style={{ fontSize: 11, color: 'var(--color-text-muted)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            — {lastStep}
          </span>
        )}
        {status === 'WAITING_HUMAN' && (
          <span style={{ fontSize: 11, color: cfg.color, fontWeight: 700 }}>→</span>
        )}
      </div>

      <style>{`
        @keyframes agent-pulse-strip {
          from { opacity: 0.6; }
          to   { opacity: 1; }
        }
        @keyframes agent-pulse-capsule {
          from { box-shadow: 0 4px 24px rgba(0,0,0,0.25); }
          to   { box-shadow: 0 4px 32px rgba(245,166,35,0.35); }
        }
        @keyframes agent-dot-pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%       { transform: scale(1.4); opacity: 0.7; }
        }
      `}</style>
    </>
  )
}
