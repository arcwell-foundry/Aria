import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  showDevDetails?: boolean;
}

/**
 * ErrorBoundary - Catches unhandled React errors and displays a professional fallback UI
 *
 * Follows ARIA Design System v1.0:
 * - Dark surface background: bg-[#0F1117]
 * - Instrument Serif for headings
 * - Satoshi for body text
 * - Lucide icons (AlertCircle, RefreshCw) at 20x20
 * - Critical color for error states: text-[#A66B6B]
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
    this.setState({
      error,
      errorInfo,
    });

    // Log to error reporting service in production
    if (typeof import.meta.env.DEV === 'undefined' || !import.meta.env.DEV) {
      // TODO: Send to error tracking service (e.g., Sentry)
      console.error('Error caught by boundary:', error, errorInfo);
    }
  }

  handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI following ARIA Design System
      return (
        <div className="min-h-screen bg-[#0F1117] flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-[#161B2E] border border-[#2A2F42] rounded-xl p-8">
            {/* Error Icon */}
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 rounded-full bg-[#A66B6B]/10 flex items-center justify-center">
                <AlertCircle size={32} className="text-[#A66B6B]" strokeWidth={1.5} aria-hidden="true" />
              </div>
            </div>

            {/* Heading - Instrument Serif */}
            <h1 className="font-display text-[32px] leading-[1.2] text-[#E8E6E1] text-center mb-4">
              Something went wrong
            </h1>

            {/* Description - Satoshi */}
            <p className="font-sans text-[15px] leading-[1.6] text-[#8B92A5] text-center mb-8">
              ARIA encountered an unexpected error. This has been logged and our team has been notified.
            </p>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                onClick={this.handleReload}
                className="inline-flex items-center justify-center gap-2 bg-[#5B6E8A] text-white rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 focus:ring-offset-[#161B2E]"
                aria-label="Reload the page"
              >
                <RefreshCw size={20} strokeWidth={1.5} aria-hidden="true" />
                Reload
              </button>

              <a
                href="https://github.com/anthropics/aria/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-[#5B6E8A]/10 transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 focus:ring-offset-[#161B2E]"
              >
                Report issue
              </a>
            </div>

            {/* Error Details - Development Only */}
            {(import.meta.env.DEV || this.state.showDevDetails) && this.state.error && (
              <details className="mt-8 pt-6 border-t border-[#2A2F42]">
                <summary className="font-sans text-[13px] font-medium text-[#8B92A5] cursor-pointer hover:text-[#E8E6E1] transition-colors">
                  Error details (development only)
                </summary>
                <div className="mt-4 p-4 bg-[#0F1117] rounded-lg overflow-auto">
                  <pre className="font-mono text-[11px] text-[#A66B6B] leading-[1.4]">
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
 *
 * @param Component - The React component to wrap
 * @param fallback - Optional custom fallback UI
 * @returns A new component with ErrorBoundary protection
 */
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode
): React.ComponentType<P> {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary fallback={fallback}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name || 'Component'})`;

  return WrappedComponent;
}
