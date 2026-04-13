import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { connectTaskWs, tasks } from '../api'

// Import the dynamic dispatcher
import HILDispatcher from '../components/hil/HILDispatcher.jsx'

const ALL_STEPS = [
  "parse_excel", "classify_assets", "fetch_cloud_album", "run_ai_detection",
  "bind_design_images", "request_annotation", "validate_quantity", "ocr_receipt",
  "match_receipts", "request_receipt_confirm", "generate_ppt", "submit_review"
]

export default function TaskExecutor() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  const [state, setState] = useState({
    status: 'CONNECTING',
    current_step: 0,
    trace_id: '-',
    ui_component: null,
    reasoning_summary: null,
    prefill: null
  })

  const [reconnectCount, setReconnectCount] = useState(0)

  useEffect(() => {
    let ws
    const connect = () => {
      ws = connectTaskWs(id, (msg) => {
        if (msg.type === 'reconnect_attempt') {
          // WS closed, reconnect
          setReconnectCount(c => c + 1)
          return
        }
        // Handle Hydration + Updates + Progress
        if (['hydration', 'task_update'].includes(msg.type)) {
          setState(s => ({ ...s, ...msg }))
          
          // Fetch specific payload for HIL state immediately if we enter human block
          if (msg.status === 'WAITING_HUMAN') {
             tasks.getHilState(id).then(res => {
                if (res?.hil) {
                   setState(s => ({ ...s, 
                     ui_component: res.hil.ui_component || s.ui_component,
                     reasoning_summary: res.hil.reasoning_summary || s.reasoning_summary,
                     prefill: res.hil.prefill || {} 
                   }))
                }
             }).catch(console.error)
          }
          
        } else if (msg.type === 'progress') {
          console.log('Progress:', msg.payload)
        } else if (msg.type === 'error') {
          console.error('WS Error:', msg)
          setState(s => ({...s, status: 'ERROR'}))
        }
      })
    }
    connect()
    return () => { if (ws) ws.close() }
  }, [id, reconnectCount])

  const handleHilSubmit = async (payloadData) => {
     try {
        await tasks.submitHil(id, {
           ui_component: state.ui_component,
           data: payloadData
        })
        // Optimistically set to running so WS refresh will hydrate properly
        setState(s => ({ ...s, status: 'RUNNING', prefill: null }))
     } catch(e) {
        alert("提交交互失败: " + String(e))
     }
  }

  const curIdx = state.current_step || 0

  return (
    <div className="flex-col gap-24">
      <div className="page-header">
        <h1>任务执行流水线 <span className={`badge badge-${state.status === 'WAITING_HUMAN' ? 'warn' : state.status} ml-16 text-sm`}>{state.status}</span></h1>
        <div className="text-sm text-muted">ID: {id} | 追踪码: {state.trace_id}</div>
      </div>

      {state.status === 'WAITING_HUMAN' && (
        <div className="hil-banner">
          ⚠️ <b>需要人工介入：</b> {state.reasoning_summary || '请提供输入以继续流程。'}
        </div>
      )}

      <div className="app-shell-split flex gap-24">
        {/* Left: Component Area */}
        <div className="flex-col w-full" style={{ flex: 2 }}>
          <div className="card w-full" style={{ minHeight: 400, padding: state.status === 'WAITING_HUMAN' ? '16px' : undefined }}>
            {state.status === 'WAITING_HUMAN' ? (
              // Use the new HIL suite if prefill loaded, else spin
              state.prefill ? (
                <HILDispatcher ui={state.ui_component} taskId={id} prefill={state.prefill} onSubmit={handleHilSubmit} />
              ) : (
                <div className="flex justify-center p-48"><div className="spinner"></div><span className="ml-16">加载上下文中...</span></div>
              )
            ) : (
              <div className="empty-state" style={{ height: '100%', justifyContent: 'center' }}>
                {state.status === 'RUNNING' ? (
                  <>
                    <div className="spinner" style={{ width: 40, height: 40, borderWidth: 3 }}></div>
                    <h3 className="mt-24">AI Agent 正在思考...</h3>
                    <p>正在执行：{ALL_STEPS[curIdx]}</p>
                  </>
                ) : state.status === 'COMPLETED' ? (
                  <>
                    <div className="empty-icon text-success">✅</div>
                    <h3>任务执行成功</h3>
                    <p>报告已生成并提交审核。</p>
                    <button className="btn btn-primary mt-16" onClick={() => navigate(-1)}>返回上一页</button>
                  </>
                ) : (
                  <>
                    <div className="empty-icon text-muted">⏳</div>
                    <h3>正在连接 Agent 引擎</h3>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right: Steps Tracker */}
        <div className="card" style={{ flex: 1, minWidth: 250 }}>
          <h3 className="mb-24">执行链路 (Trace)</h3>
          <div className="stepper">
            {ALL_STEPS.map((step, idx) => {
              const isActive = idx === curIdx && state.status === 'RUNNING'
              const isWaiting = idx === curIdx && (state.status === 'WAITING_HUMAN' || state.status === 'PAUSED_HIL')
              const isDone = idx < curIdx || state.status === 'COMPLETED'
              
              const dotClass = isDone ? 'done' : isWaiting ? 'waiting' : isActive ? 'active' : 'pending'
              
              return (
                 <div key={step} className="step-item">
                   <div className={`step-dot ${dotClass}`}>{isDone ? '✓' : idx + 1}</div>
                   <div className="step-content border-l border-transparent">
                     <div className={`step-name ${isActive || isWaiting ? 'text-primary' : isDone ? 'text-text' : 'text-muted'}`}>
                       {step}
                     </div>
                     {(isActive || isWaiting) && <div className="step-detail text-xs mt-4">{isWaiting ? '等待人工确认中' : '运行 AI 进程...'}</div>}
                   </div>
                 </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
