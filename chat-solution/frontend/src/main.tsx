import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../../frontend/src/index.css'
import ChatApp from '../../../frontend/src/apps/ChatApp'
import { ErrorBoundary } from '../../../frontend/src/components/ErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ChatApp />
    </ErrorBoundary>
  </StrictMode>,
)
