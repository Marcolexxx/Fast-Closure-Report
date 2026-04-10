import { useState } from 'react'

// Low confidence field badge
function LowConfBadge({ fields }) {
  if (!fields || Object.keys(fields).length === 0) return null
  const names = Object.keys(fields).join(', ')
  return (
    <span
      title={`低置信字段：${JSON.stringify(fields)}`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        fontSize: 10, padding: '2px 6px', borderRadius: 10,
        background: 'rgba(245,166,35,0.15)', color: 'var(--color-warn, #f5a623)',
        border: '1px solid var(--color-warn, #f5a623)', cursor: 'help',
        marginLeft: 6, fontWeight: 600,
      }}
    >
      ⚠ 低置信: {names}
    </span>
  )
}

// Void invoice badge (冲红发票)
function VoidBadge({ isVoid }) {
  if (!isVoid) return null
  return (
    <span style={{
      fontSize: 10, padding: '2px 6px', borderRadius: 10,
      background: 'rgba(255,59,48,0.15)', color: 'var(--color-danger, #ff3b30)',
      border: '1px solid var(--color-danger, #ff3b30)', marginLeft: 4, fontWeight: 700,
    }}>
      冲红
    </span>
  )
}

export default function ReceiptMatcher({ taskId, prefill, onSubmit }) {
  const [matches, setMatches] = useState(() => prefill?.receipts?.matches || [])
  const [unmatched, setUnmatched] = useState(() => prefill?.receipts?.unmatched || [])
  // Track which unmatched items user has manually dismissed (skipped)
  const [dismissed, setDismissed] = useState(new Set())

  const handleSubmit = () => {
    // Include only non-dismissed unmatched
    const finalUnmatched = unmatched.filter((_, i) => !dismissed.has(i))
    onSubmit({
      resolved_matches: matches,
      final_unmatched: finalUnmatched,
      dismissed_count: dismissed.size,
    })
  }

  const handleOverrideScore = (idx) => {
    const arr = [...matches]
    arr[idx] = { ...arr[idx], confirmed_by: 'human_override' }
    setMatches(arr)
  }

  const handleRejectMatch = (idx) => {
    // Move rejected match back to unmatched list
    const rejected = matches[idx]
    setMatches(prev => prev.filter((_, i) => i !== idx))
    if (rejected.payment) setUnmatched(prev => [...prev, rejected.payment])
    if (rejected.invoice) setUnmatched(prev => [...prev, rejected.invoice])
  }

  const handleDismissUnmatched = (idx) => {
    setDismissed(prev => new Set([...prev, idx]))
  }

  const pendingUnmatched = unmatched.filter((_, i) => !dismissed.has(i))
  const hasWarning = matches.some(m => m.amount_diff > 0 || m.date_diff_days > 15)

  return (
    <div className="flex-col gap-24">
      {/* Summary Bar */}
      <div style={{
        display: 'flex', gap: 16, padding: '12px 16px',
        background: 'var(--color-surface-2)', borderRadius: 10,
        border: '1px solid var(--color-border)', alignItems: 'center',
      }}>
        <span className="text-sm">
          AI 匹配 <b style={{ color: 'var(--color-success)' }}>{matches.length}</b> 对 ·
          未匹配 <b style={{ color: pendingUnmatched.length ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>
            {pendingUnmatched.length}
          </b> 条
          {dismissed.size > 0 && <span className="text-muted text-xs ml-8">（已跳过 {dismissed.size} 条）</span>}
        </span>
        {hasWarning && (
          <span style={{ fontSize: 12, color: 'var(--color-warn)', fontWeight: 600 }}>
            ⚠ 含弱匹配需确认
          </span>
        )}
      </div>

      {/* Matched Pairs */}
      <div className="card">
        <h3 className="mb-16">已匹配凭据对（需审查）</h3>
        {matches.length === 0 ? (
          <div className="text-muted text-sm">未发现匹配。</div>
        ) : (
          <table className="data-table" style={{ fontSize: 13 }}>
            <thead>
              <tr>
                <th>付款凭证</th>
                <th>发票</th>
                <th>金额差</th>
                <th>日期差</th>
                <th>类型</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m, i) => {
                const amtDiff = parseFloat(m.amount_diff || 0)
                const isWarn = Math.abs(amtDiff) > 0.01 || (m.date_diff_days || 0) > 15
                const pmt = m.payment || {}
                const inv = m.invoice || {}
                const pmtLowConf = pmt.low_confidence_fields || {}
                const invLowConf = inv.low_confidence_fields || {}

                return (
                  <tr key={i} style={m.confirmed_by ? { background: 'rgba(52,199,89,0.06)' } : {}}>
                    <td>
                      <div className="font-bold">
                        ￥{pmt.amount}
                        <VoidBadge isVoid={pmt.is_void} />
                        <LowConfBadge fields={pmtLowConf} />
                      </div>
                      <div className="text-xs text-muted">{pmt.date} · {pmt.merchant || '—'}</div>
                    </td>
                    <td>
                      <div className="font-bold">
                        ￥{inv.amount}
                        <VoidBadge isVoid={inv.is_void} />
                        <LowConfBadge fields={invLowConf} />
                      </div>
                      <div className="text-xs text-muted">{inv.date} · #{inv.invoice_no || '—'}</div>
                    </td>
                    <td className={Math.abs(amtDiff) > 0.01 ? 'text-danger font-bold' : 'text-success'}>
                      {amtDiff > 0 ? '+' : ''}{amtDiff.toFixed(2)}
                    </td>
                    <td className={(m.date_diff_days || 0) > 15 ? 'text-warn' : ''}>
                      {m.date_diff_days ?? '—'} 天
                    </td>
                    <td>
                      <span className={`badge ${isWarn ? 'badge-warn' : 'badge-success'}`}>
                        {m.match_type || 'EXACT'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {!m.confirmed_by && isWarn && (
                          <button id={`receipt-accept-${i}`} className="btn btn-ghost btn-sm" onClick={() => handleOverrideScore(i)}>
                            接受弱匹配
                          </button>
                        )}
                        {m.confirmed_by ? (
                          <span className="text-xs text-success font-bold">✓ 已确认</span>
                        ) : (
                          <button id={`receipt-reject-${i}`} className="btn btn-ghost btn-sm text-danger" onClick={() => handleRejectMatch(i)}>
                            驳回
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Unmatched / Anomalies */}
      <div className="card" style={{ border: `1px dashed var(--color-warn)` }}>
        <h3 className="mb-16" style={{ color: 'var(--color-warn)' }}>
          未匹配 / 异常凭据 ({pendingUnmatched.length})
        </h3>
        {pendingUnmatched.length === 0 ? (
          <div className="text-muted text-sm">无未匹配凭据。✅</div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {unmatched.map((u, i) => {
              if (dismissed.has(i)) return null
              const lowConf = u.low_confidence_fields || {}
              return (
                <div
                  key={i}
                  style={{
                    padding: 16, borderRadius: 10, width: 230,
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span className="badge badge-draft">{u.type || 'receipt'}</span>
                    <span style={{ fontWeight: 700, color: u.is_void ? 'var(--color-danger)' : 'var(--color-text)' }}>
                      ￥{u.amount || '???'}
                      {u.is_void && <VoidBadge isVoid />}
                    </span>
                  </div>
                  <div className="text-xs text-muted">日期: {u.date || '未知'}</div>
                  <div className="text-xs text-muted truncate">商户: {u.merchant || '—'}</div>
                  {Object.keys(lowConf).length > 0 && <LowConfBadge fields={lowConf} />}
                  <button
                    id={`unmatched-dismiss-${i}`}
                    className="btn btn-ghost btn-sm w-full mt-8"
                    style={{ fontSize: 11 }}
                    onClick={() => handleDismissUnmatched(i)}
                  >
                    跳过此凭据
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 16 }}>
        <button id="receipt-confirm-btn" className="btn btn-primary" onClick={handleSubmit}>
          确认账目 &amp; 继续生成 PPT
        </button>
      </div>
    </div>
  )
}

