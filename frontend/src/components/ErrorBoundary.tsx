import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw, RotateCcw } from 'lucide-react';
import { reportErrorToBackend } from '@/api/errorHandler';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * ErrorBoundary - Catches unhandled React errors and displays a professional fallback UI
 *
 * Features:
 * - Retry button that resets error state without a full page reload
 * - Reload button for hard recovery
 * - Automatically logs errors to POST /api/v1/feedback/general with type='bug'
 *
 * Follows ARIA Design System v1.0:
 * - Dark surface background: bg-primary
 * - Instrument Serif for headings
 * - Satoshi for body text
 * - Lucide icons at 20x20
 * - Critical color for error states: text-critical
 * - Accessible with ARIA labels and keyboard navigation
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(): Partial<State> {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ error, errorInfo });

    // Report to backend feedback endpoint
    const context = `ErrorBoundary catch — component stack: ${errorInfo.componentStack?.slice(0, 500) ?? "unknown"}`;
    reportErrorToBackend(error, context);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-primary flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-elevated border border-border rounded-xl p-8">
            {/* Error Icon */}
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 rounded-full bg-critical/10 flex items-center justify-center">
                <AlertCircle size={32} className="text-critical" strokeWidth={1.5} aria-hidden="true" />
              </div>
            </div>

            {/* Heading */}
            <h1 className="font-display text-[32px] leading-[1.2] text-content text-center mb-4">
              Something went wrong
            </h1>

            {/* Description */}
            <p className="font-sans text-[15px] leading-[1.6] text-secondary text-center mb-8">
              ARIA encountered an unexpected error. This has been logged automatically and our team has been notified.
            </p>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                onClick={this.handleRetry}
                className="inline-flex items-center justify-center gap-2 bg-interactive text-white rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-elevated"
                aria-label="Try again without reloading"
              >
                <RotateCcw size={20} strokeWidth={1.5} aria-hidden="true" />
                Try again
              </button>

              <button
                onClick={this.handleReload}
                className="inline-flex items-center justify-center gap-2 bg-transparent border border-border text-secondary rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-white/5 hover:text-content transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-elevated"
                aria-label="Reload the page"
              >
                <RefreshCw size={20} strokeWidth={1.5} aria-hidden="true" />
                Reload page
              </button>
            </div>

            {/* Error Details - Development Only */}
            {import.meta.env.DEV && this.state.error && (
              <details className="mt-8 pt-6 border-t border-border">
                <summary className="font-sans text-[13px] font-medium text-secondary cursor-pointer hover:text-content transition-colors">
                  Error details (development only)
                </summary>
                <div className="mt-4 p-4 bg-primary rounded-lg overflow-auto">
                  <pre className="font-mono text-[11px] text-critical leading-[1.4]">
                    {this.state.error.toString()}
                    {this.state.errorInfo?.componentStack}
                  </pre>
                </div>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * HOC wrapper for adding ErrorBoundary to any component
 */
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode,
): React.ComponentType<P> {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary fallback={fallback}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name || 'Component'})`;

  return WrappedComponent;
}
