import type { ReactNode } from 'react'
import { Component } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
  stack: string
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '', stack: '' }

  static getDerivedStateFromError(error: unknown): Partial<State> {
    const message = error instanceof Error ? error.message : String(error)
    return { hasError: true, message }
  }

  componentDidCatch(error: unknown) {
    const stack = error instanceof Error ? error.stack ?? '' : ''
    this.setState((prev) => ({ ...prev, stack }))
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background text-foreground p-6">
          <div className="max-w-3xl mx-auto space-y-3">
            <h1 className="text-xl font-bold">Application error</h1>
            <p className="text-sm text-red-500" data-testid="app-error-message">
              {this.state.message}
            </p>
            {this.state.stack && (
              <pre
                className="text-xs p-3 rounded bg-card border border-border overflow-auto"
                data-testid="app-error-stack"
              >
                {this.state.stack}
              </pre>
            )}
            <p className="text-sm text-muted-foreground">
              Reload the page. If the error persists, copy the message/stack above.
            </p>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
