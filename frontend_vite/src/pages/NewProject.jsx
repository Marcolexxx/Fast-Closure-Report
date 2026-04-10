import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { projects, tasks } from '../api'

export default function NewProject() {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState('')
  const [files, setFiles] = useState([])
  const navigate = useNavigate()

  const handleFileSelect = (e) => {
    setFiles(Array.from(e.target.files))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      // 1. Create project
      const proj = await projects.create({ name, description: desc })
      
      // 2. Upload files
      const uploads = []
      const CHUNK_SIZE = 5 * 1024 * 1024 // 5MB
      
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        setUploadProgress(`正在准备上传: ${file.name} (${i+1}/${files.length})`)
        const fileHash = `${file.name}_${file.size}_${file.lastModified || 0}`
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
        
        const initRes = await projects.uploadInit(proj.id, {
          filename: file.name,
          file_size: file.size,
          total_chunks: totalChunks,
          file_hash: fileHash
        })
        
        const uploadId = initRes.upload_id
        const uploadedChunks = new Set(initRes.uploaded_chunks || [])
        
        let sentChunks = uploadedChunks.size
        for (let chunkIdx = 0; chunkIdx < totalChunks; chunkIdx++) {
          if (uploadedChunks.has(chunkIdx)) continue
          
          const start = chunkIdx * CHUNK_SIZE
          const end = Math.min(start + CHUNK_SIZE, file.size)
          const blob = file.slice(start, end)
          
          await projects.uploadChunk(proj.id, uploadId, chunkIdx, blob)
          
          sentChunks++
          setUploadProgress(`文件 ${i+1}/${files.length} : ${file.name} (${Math.round(sentChunks / totalChunks * 100)}%)`)
        }
        
        setUploadProgress(`正在合并文件: ${file.name}...`)
        const finalFile = await projects.uploadComplete(proj.id, {
          upload_id: uploadId,
          filename: file.name,
          file_size: file.size,
          total_chunks: totalChunks
        })
        uploads.push(finalFile)
      }
      
      setUploadProgress('正在启动 AI 管线...')
      // 3. Create agent task
      const taskRes = await tasks.create({
        skill_id: 'skill-event-report', // Currently hardcoded to our first skill
        context: {
          project_id: proj.id,
          uploaded_files: uploads
        }
      })
      
      // Link task to project in DB (Mocked via API logic internally or just proceed)
      
      navigate(`/tasks/${taskRes.task_id}`)
    } catch (err) {
      console.error(err)
      alert(err?.detail || '创建项目失败')
    } finally {
      setLoading(false)
      setUploadProgress('')
    }
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <div className="page-header">
        <h1>发起新任务</h1>
      </div>
      
      <div className="card">
        <form onSubmit={handleSubmit} className="flex-col gap-24">
          <div className="form-group">
            <label className="form-label">项目名称</label>
            <input 
              type="text" 
              className="input" 
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder="例如：2026 年度科技大会"
              required 
            />
          </div>
          
          <div className="form-group">
            <label className="form-label">项目描述（可选）</label>
            <textarea 
              className="input" 
              value={desc} 
              onChange={e => setDesc(e.target.value)} 
              placeholder="补充给 AI Agent 的任何背景信息..."
            />
          </div>

          <div className="form-group mt-8">
            <label className="form-label">上传资源附件</label>
            <p className="text-sm text-muted mb-16">
              请上传 Excel BOM 表格、设计图纸（.jpg/.png）或者费用凭证等压缩包（.pdf/.zip）。
            </p>
            <label className="dropzone">
              <input type="file" multiple onChange={handleFileSelect} className="hidden" style={{ display: 'none' }}/>
              <div className="dropzone-icon">☁️</div>
              <div className="font-bold">点击浏览文件，或将文件拖拽到此处</div>
              <div className="dropzone-hint">支持 xlsx, png, jpg, pdf, zip (最大 50MB)</div>
            </label>
            {files.length > 0 && (
              <div className="mt-16 text-sm">
                <div className="font-bold mb-8">已选择文件 ({files.length}):</div>
                <div className="flex-col gap-4">
                  {files.map(f => (
                    <div key={f.name} className="flex justify-between items-center bg-[var(--color-surface-2)] p-2 rounded">
                      <span className="truncate" style={{ maxWidth: 300 }}>{f.name}</span>
                      <span className="text-muted text-xs">{(f.size/1024/1024).toFixed(1)} MB</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-between items-center mt-16 pt-16 border-t border-[var(--color-border)]">
            <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)} disabled={loading}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading || !name}>
              {loading ? (
                <div className="flex items-center">
                  <div className="spinner mr-8"></div>
                  {uploadProgress || '处理中...'}
                </div>
              ) : '启动 AI 分析'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
