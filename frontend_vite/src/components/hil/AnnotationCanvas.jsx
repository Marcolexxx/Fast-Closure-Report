import { useState, useRef, useEffect, useCallback } from 'react'
import { fabric } from 'fabric'
import { Undo2, Redo2, Eraser, Square, RefreshCw } from 'lucide-react'

// ── IndexedDB helpers for draft persistence (PRD §7.2) ─────────────────────
const IDB_NAME = 'aicopilot_drafts'
const IDB_STORE = 'annotations'

function openDraftDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1)
    req.onupgradeneeded = (e) => e.target.result.createObjectStore(IDB_STORE)
    req.onsuccess = (e) => resolve(e.target.result)
    req.onerror = reject
  })
}

async function saveDraft(taskId, data) {
  try {
    const db = await openDraftDb()
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).put({ data, savedAt: Date.now() }, taskId)
  } catch {}
}

async function loadDraft(taskId) {
  try {
    const db = await openDraftDb()
    return await new Promise((resolve) => {
      const req = db.transaction(IDB_STORE).objectStore(IDB_STORE).get(taskId)
      req.onsuccess = () => resolve(req.result || null)
      req.onerror = () => resolve(null)
    })
  } catch { return null }
}

async function clearDraft(taskId) {
  try {
    const db = await openDraftDb()
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).delete(taskId)
  } catch {}
}
// ──────────────────────────────────────────────────────────────────────────────

export default function AnnotationCanvas({ taskId, prefill, onSubmit }) {

  const [images] = useState(() => prefill?.assets || [])
  const [activeIndex, setActiveIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [draftRestored, setDraftRestored] = useState(false)

  const canvasEl = useRef(null)
  const canvasInst = useRef(null)
  const autosaveTimer = useRef(null)
  const activeImage = images[activeIndex]

  // We maintain a simple history stack of drawing states (Command pattern)
  const [history, setHistory] = useState([])
  const [historyIdx, setHistoryIdx] = useState(-1)
  
  const saveState = useCallback(() => {
    if (!canvasInst.current) return
    const state = canvasInst.current.getObjects().map(o => o.toObject())
    const newHist = history.slice(0, historyIdx + 1)
    newHist.push(state)
    // Max 20 steps
    if (newHist.length > 20) newHist.shift()
    setHistory(newHist)
    setHistoryIdx(newHist.length - 1)
  }, [history, historyIdx])

  // PRD §7.2: 30s IndexedDB auto-save draft
  useEffect(() => {
    if (!taskId) return
    autosaveTimer.current = setInterval(async () => {
      if (!canvasInst.current) return
      const draftData = {
        activeIndex,
        objects: canvasInst.current.getObjects().map(o => o.toObject()),
        savedAt: Date.now(),
      }
      await saveDraft(taskId, draftData)
    }, 30_000)
    return () => clearInterval(autosaveTimer.current)
  }, [taskId, activeIndex])

  useEffect(() => {
    if (!canvasEl.current || !activeImage) return
    
    // Cleanup previous instance
    if (canvasInst.current) {
      canvasInst.current.dispose()
    }
    
    setLoading(true)
    const c = new fabric.Canvas(canvasEl.current, {
      selection: true,
      preserveObjectStacking: true,
      backgroundColor: '#131620'
    })
    
    canvasInst.current = c
    c.on('object:modified', saveState)

    // Load Image
    fabric.Image.fromURL(activeImage.url || '', async (img) => {
      if (!img) { setLoading(false); return }
      
      const scale = Math.min(
        800 / (img.width || 800),
        600 / (img.height || 600)
      )
      
      c.setWidth((img.width || 800) * scale)
      c.setHeight((img.height || 600) * scale)
      
      img.scale(scale)
      img.set({ selectable: false, evented: false })
      c.setBackgroundImage(img, c.renderAll.bind(c))

      // PRD §7.2: Try restoring IndexedDB draft first
      let restored = false
      if (taskId && !draftRestored) {
        const draft = await loadDraft(taskId)
        if (draft?.data?.objects?.length) {
          fabric.util.enlivenObjects(draft.data.objects, (objects) => {
            objects.forEach(o => c.add(o))
            c.renderAll()
          })
          setDraftRestored(true)
          restored = true
        }
      }

      if (!restored) {
        // Load prefill AI candidates
        const aiBoxes = activeImage.candidates || []
        aiBoxes.forEach(b => {
          const rect = new fabric.Rect({
            left: b.x * c.width,
            top: b.y * c.height,
            width: b.w * c.width,
            height: b.h * c.height,
            fill: 'transparent',
            stroke: (b.confidence ?? 0.5) > 0.7 ? '#34c759' : '#f5a623',
            strokeWidth: 2,
            selectable: true,
            data: { source: 'ai', confidence: b.confidence },
          })
          c.add(rect)
        })
      }
      
      setLoading(false)
      if (historyIdx === -1) {
        setHistory([c.getObjects().map(o => o.toObject())])
        setHistoryIdx(0)
      }
    })
    
    return () => {
      c.off()
      c.dispose()
      canvasInst.current = null
    }
  }, [activeIndex]) // rebuild on image switch
  
  const addRect = () => {
    const c = canvasInst.current
    if (!c) return
    const rect = new fabric.Rect({
      left: 50, top: 50, width: 100, height: 100,
      fill: 'transparent', stroke: '#7c6ef5', strokeWidth: 3,
      selectable: true
    })
    c.add(rect)
    c.setActiveObject(rect)
    saveState()
  }

  const deleteActive = () => {
    const c = canvasInst.current
    if (!c) return
    const active = c.getActiveObjects()
    if (active.length) {
      c.remove(...active)
      c.discardActiveObject()
      saveState()
    }
  }

  const handleUndo = () => {
    if (historyIdx > 0 && canvasInst.current) {
      const idx = historyIdx - 1
      const state = history[idx]
      // Preserve background image, remove only drawn objects
      const bg = canvasInst.current.backgroundImage
      canvasInst.current.clear()
      if (bg) canvasInst.current.setBackgroundImage(bg, canvasInst.current.renderAll.bind(canvasInst.current))
      // Fix: correct Fabric.js API is enlivenObjects (not enlivablesProcess)
      fabric.util.enlivenObjects(state, (objects) => {
        canvasInst.current.add(...objects)
        canvasInst.current.renderAll()
      })
      setHistoryIdx(idx)
    }
  }

  const handleComplete = () => {
    const c = canvasInst.current
    if (!c) return
    // Generate normalized coords; only include is_confirmed objects (exclude pure AI candidates)
    const coords = c.getObjects().map(o => ({
      x: o.left / c.width,
      y: o.top / c.height,
      w: (o.width * (o.scaleX || 1)) / c.width,
      h: (o.height * (o.scaleY || 1)) / c.height,
      confidence: 1.0, // user confirmed
      source: o.data?.source || 'human',
    }))
    
    // Experience Layer — fire and forget
    import('../../api').then(m => {
      m.feedback.submit({
        task_id: taskId,
        skill_id: 'skill-event-report',
        event_type: 'annotation_corrected',
        payload_json: {
          image_id: activeImage.id,
          final_count: coords.length,
          ai_candidate_count: (activeImage.candidates || []).length,
        },
      }).catch(() => {})
    }).catch(() => {})

    // PRD §7.2: clear draft after confirmed submit
    if (taskId) clearDraft(taskId)

    onSubmit({ image_id: activeImage.id, annotations: coords })
  }

  if (!images.length) return <div>No images to annotate.</div>

  return (
    <div className="flex gap-16" style={{ height: '100%' }}>
      {/* Left List */}
      <div className="flex-col gap-8 w-1/4" style={{ minWidth: 200, borderRight: '1px solid var(--color-border)', paddingRight: 16 }}>
        <h4 className="mb-8">Images ({images.length})</h4>
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {images.map((img, i) => (
            <div 
              key={img.id || i}
              className={`p-12 mb-8 rounded cursor-pointer transition ${i === activeIndex ? 'bg-[var(--color-primary-dim)] border border-[var(--color-primary)]' : 'bg-[var(--color-surface-2)] hover:border-[var(--color-border-hi)]'}`}
              onClick={() => {
                setActiveIndex(i)
                setHistoryIdx(-1)
                setHistory([])
              }}
            >
               <div className="font-bold text-sm truncate">{img.name || `Image #${i+1}`}</div>
               <div className="text-xs text-muted mt-4">AI Detects: {img.candidates?.length||0}</div>
            </div>
          ))}
        </div>
      </div>
      
      {/* Right Canvas Area */}
      <div className="flex-col flex-1">
        <div className="annotation-toolbar mb-16 rounded shadow">
           <button className="btn btn-ghost btn-sm" onClick={addRect}><Square size={16}/> Rect</button>
           <button className="btn btn-ghost btn-sm"><Circle size={16}/> Circle</button>
           <div className="w-[1px] h-16 bg-[var(--color-border)] mx-8"></div>
           <button className="btn btn-ghost btn-sm text-danger" onClick={deleteActive}><Eraser size={16}/> Erase</button>
           <div className="w-[1px] h-16 bg-[var(--color-border)] mx-8"></div>
           <button className="btn btn-ghost btn-sm" onClick={handleUndo} disabled={historyIdx <= 0}><Undo2 size={16}/> Undo</button>
           <button className="btn btn-ghost btn-sm" disabled><Redo2 size={16}/> Redo</button>
        </div>
        
        <div className="annotation-canvas-wrap flex justify-center items-center flex-1 bg-black rounded" style={{ minHeight: 600 }}>
          {loading && <div className="absolute"><div className="spinner"></div></div>}
          <canvas ref={canvasEl} />
        </div>
        
        <div className="flex justify-between items-center mt-16 pt-16 border-t border-[var(--color-border)]">
          <div className="text-sm text-muted">
             {canvasInst.current ? `${canvasInst.current.getObjects().length} boxes drawn` : 'Ready'}
          </div>
          <button className="btn btn-primary" onClick={handleComplete}>
            Confirm & Save Annotations
          </button>
        </div>
      </div>
    </div>
  )
}
