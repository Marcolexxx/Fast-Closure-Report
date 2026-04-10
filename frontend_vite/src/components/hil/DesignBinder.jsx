import { useState, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

export default function DesignBinder({ taskId, prefill, onSubmit }) {
  // prefill structure: { items: [], design_images: [] }
  const [items, setItems] = useState(() => prefill?.items || [])
  const [images] = useState(() => prefill?.design_images || [])
  
  // Track bindings: item_id -> array of image objects
  const [bindings, setBindings] = useState({})
  
  const [activeItemIdx, setActiveItemIdx] = useState(0)

  // Virtualizer for the large design image waterfall
  const parentRef = useRef()
  const rowVirtualizer = useVirtualizer({
    count: Math.ceil(images.length / 3), // 3 columns
    getScrollElement: () => parentRef.current,
    estimateSize: () => 180, // estimated row height
  })

  const activeItem = items[activeItemIdx]

  const toggleBind = (img) => {
    if (!activeItem) return
    const id = activeItem.id || activeItem.name
    setBindings(prev => {
      const current = prev[id] || []
      const exists = current.find(x => x.id === img.id)
      if (exists) {
        return { ...prev, [id]: current.filter(x => x.id !== img.id) }
      } else {
        return { ...prev, [id]: [...current, img] }
      }
    })
  }

  const handleSubmit = () => {
    // Generate mapping JSON
    const payload = items.map(it => {
      const id = it.id || it.name
      return {
        item_id: id,
        item_name: it.name,
        design_image_paths: (bindings[id] || []).map(img => img.local_path)
      }
    })
    onSubmit({ mappings: payload })
  }

  return (
    <div className="flex gap-24 h-[600px]" style={{ height: 600 }}>
      {/* Left: Material Tree */}
      <div className="flex-col w-1/3 bg-[var(--color-surface-2)] p-16 rounded border border-[var(--color-border)]">
        <h4 className="mb-16">Materials ({items.length})</h4>
        <div style={{ overflowY: 'auto', flex: 1 }} className="flex-col gap-8">
          {items.map((it, idx) => {
            const id = it.id || it.name
            const boundCount = (bindings[id] || []).length
            return (
              <div 
                key={id}
                className={`p-12 rounded cursor-pointer transition flex justify-between items-center
                  ${idx === activeItemIdx ? 'bg-[var(--color-primary-dim)] border border-[var(--color-primary)]' : 'bg-transparent hover:bg-[var(--glass-bg)] border border-transparent'}`}
                onClick={() => setActiveItemIdx(idx)}
              >
                <div>
                  <div className="text-sm font-bold truncate" style={{ maxWidth: 180 }}>{it.name}</div>
                  <div className="text-xs text-muted mt-4">Target: {it.target_qty}</div>
                </div>
                {boundCount > 0 && <span className="badge badge-COMPLETED">{boundCount} Bound</span>}
              </div>
            )
          })}
        </div>
      </div>

      {/* Right: Design Images Waterfall */}
      <div className="flex-col flex-1">
        <h4 className="mb-16">Design Library ({images.length}) - Select to bind to {activeItem?.name}</h4>
        
        <div ref={parentRef} style={{ height: 'calc(100% - 100px)', overflowY: 'auto' }} className="rounded border border-[var(--color-border)] p-16 bg-[var(--glass-bg)]">
          <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }}>
            {rowVirtualizer.getVirtualItems().map((vRow) => (
               <div
                 key={vRow.key}
                 style={{
                   position: 'absolute',
                   top: 0,
                   left: 0,
                   width: '100%',
                   height: `${vRow.size}px`,
                   transform: `translateY(${vRow.start}px)`,
                   display: 'grid',
                   gridTemplateColumns: 'repeat(3, 1fr)',
                   gap: '16px'
                 }}
               >
                 {[0, 1, 2].map(colIdx => {
                   const imgIdx = vRow.index * 3 + colIdx
                   const img = images[imgIdx]
                   if (!img) return <div key={colIdx} />
                   
                   const activeId = activeItem?.id || activeItem?.name
                   const isBoundToCurrent = (bindings[activeId] || []).find(x => x.id === img.id)
                   
                   return (
                     <div 
                       key={img.id} 
                       className={`rounded overflow-hidden cursor-pointer relative border-2 transition
                         ${isBoundToCurrent ? 'border-[var(--color-success)] scale-[0.98]' : 'border-[var(--color-border)] hover:border-[var(--color-primary)]'}`}
                       style={{ height: 160 }}
                       onClick={() => toggleBind(img)}
                     >
                        <img src={img.url} alt="Design Render" className="w-full h-full object-cover" />
                        {isBoundToCurrent && (
                          <div className="absolute top-8 right-8 bg-[var(--color-success)] text-white w-24 h-24 rounded-full flex items-center justify-center font-bold text-xs">
                            ✓
                          </div>
                        )}
                        <div className="absolute bottom-0 left-0 right-0 bg-black/60 p-4 text-[0.7rem] truncate backdrop-blur">
                           {img.name || `Design_${img.id.slice(0,6)}`}
                        </div>
                     </div>
                   )
                 })}
               </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end mt-16 pt-16 border-t border-[var(--color-border)]">
          <button className="btn btn-primary" onClick={handleSubmit}>
            Confirm Bindings & Generate PPT
          </button>
        </div>
      </div>
    </div>
  )
}
