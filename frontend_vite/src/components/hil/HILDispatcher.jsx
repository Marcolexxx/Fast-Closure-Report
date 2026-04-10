import { Suspense, lazy } from 'react'

const AnnotationCanvas = lazy(() => import('./AnnotationCanvas'))
const DesignBinder = lazy(() => import('./DesignBinder'))
const ReceiptMatcher = lazy(() => import('./ReceiptMatcher'))

export default function HILDispatcher({ ui, taskId, prefill, onSubmit }) {
  const ComponentMap = {
    'AnnotationCanvas': AnnotationCanvas,
    'DesignBinder': DesignBinder,
    'ReceiptMatcher': ReceiptMatcher
  }
  
  const TargetComponent = ComponentMap[ui]

  if (!TargetComponent) {
    return (
      <div className="empty-state">
        <div className="empty-icon text-danger">⚠️</div>
        <h3>Unknown HIL Component</h3>
        <p>The server requested <code>{ui}</code>, which is not registered.</p>
      </div>
    )
  }

  return (
    <Suspense fallback={<div className="flex justify-center p-48"><div className="spinner"></div></div>}>
      <TargetComponent taskId={taskId} prefill={prefill} onSubmit={onSubmit} />
    </Suspense>
  )
}
