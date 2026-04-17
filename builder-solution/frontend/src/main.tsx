import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../../frontend/src/index.css'
import BuilderApp from '../../../frontend/src/apps/BuilderApp'
import { ErrorBoundary } from '../../../frontend/src/components/ErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BuilderApp />
    </ErrorBoundary>
  </StrictMode>,
)
