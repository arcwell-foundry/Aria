/**
 * Integration Tests for Error Handling Components (US-930 Task 9)
 *
 * These tests verify that error handling components work together
 * and integrate properly with the application.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ErrorBoundary } from '../../src/components/ErrorBoundary';
import { EmptyState, EmptyLeads, EmptyGoals } from '../../src/components/EmptyState';
import {
  SkeletonLoader,
  CardSkeleton,
  ListSkeleton,
  TableSkeleton,
  TextSkeleton,
  LeadsSkeleton,
} from '../../src/components/SkeletonLoader';
import { OfflineBanner } from '../../src/components/OfflineBanner';

// Test component that throws an error
const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>No error</div>;
};

// Test component that simulates async loading
const AsyncComponent = ({
  isLoading,
  data,
}: {
  isLoading: boolean;
  data: string | null;
}) => {
  if (isLoading) {
    return <LeadsSkeleton viewMode="card" count={3} />;
  }
  if (!data) {
    return <EmptyLeads />;
  }
  return <div>{data}</div>;
};

describe('Error Handling Integration Tests', () => {
  describe('ErrorBoundary Integration', () => {
    it('catches component errors and shows fallback UI', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByText('Reload')).toBeInTheDocument();
    });

    it('allows normal rendering when no error occurs', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByText('No error')).toBeInTheDocument();
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('provides custom fallback UI when provided', () => {
      const customFallback = <div>Custom error message</div>;

      render(
        <ErrorBoundary fallback={customFallback}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Custom error message')).toBeInTheDocument();
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('shows error details in development mode', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // Error details should be visible in dev mode
      const errorText = screen.queryByText(/Test error/);
      expect(errorText).toBeInTheDocument();
    });

    it('has working reload functionality', () => {
      const reloadMock = vi.fn();
      Object.defineProperty(window, 'location', {
        value: { reload: reloadMock },
        writable: true,
      });

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const reloadButton = screen.getByText('Reload');
      reloadButton.click();

      expect(reloadMock).toHaveBeenCalled();
    });

    it('provides link to report issues', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const reportLink = screen.getByText('Report issue');
      expect(reportLink).toHaveAttribute('href', 'https://github.com/anthropics/aria/issues');
      expect(reportLink).toHaveAttribute('target', '_blank');
      expect(reportLink).toHaveAttribute('rel', 'noopener noreferrer');
    });
  });

  describe('EmptyState Integration', () => {
    it('displays correctly with all required props', () => {
      render(
        <EmptyState
          icon={() => <div data-testid="test-icon">Icon</div>}
          title="No Data"
          description="There is no data to display"
        />
      );

      expect(screen.getByText('No Data')).toBeInTheDocument();
      expect(screen.getByText('There is no data to display')).toBeInTheDocument();
      expect(screen.getByTestId('test-icon')).toBeInTheDocument();
    });

    it('renders action button when actionLabel and onAction provided', () => {
      const handleAction = vi.fn();

      render(
        <EmptyState
          icon={() => <div>Icon</div>}
          title="No Items"
          description="Add items to get started"
          actionLabel="Add Item"
          onAction={handleAction}
        />
      );

      const actionButton = screen.getByText('Add Item');
      expect(actionButton).toBeInTheDocument();
      expect(actionButton.closest('button')).toBeInTheDocument();

      actionButton.click();
      expect(handleAction).toHaveBeenCalledTimes(1);
    });

    it('does not render action button without onAction handler', () => {
      render(
        <EmptyState
          icon={() => <div>Icon</div>}
          title="No Items"
          description="Add items to get started"
          actionLabel="Add Item"
        />
      );

      expect(screen.queryByText('Add Item')).not.toBeInTheDocument();
    });

    it('applies custom className correctly', () => {
      const { container } = render(
        <EmptyState
          icon={() => <div>Icon</div>}
          title="Test"
          description="Test description"
          className="custom-wrapper-class"
        />
      );

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass('custom-wrapper-class');
    });

    describe('Preset EmptyStates', () => {
      it('EmptyLeads renders with correct content', () => {
        render(<EmptyLeads />);

        expect(screen.getByText('No leads yet')).toBeInTheDocument();
        expect(
          screen.getByText(/ARIA can start finding prospects/)
        ).toBeInTheDocument();
      });

      it('EmptyGoals renders with correct content', () => {
        render(<EmptyGoals />);

        expect(screen.getByText('No goals yet')).toBeInTheDocument();
        expect(
          screen.getByText(/Set a goal and ARIA will start working/)
        ).toBeInTheDocument();
      });

      it('EmptyLeads accepts optional action props', () => {
        const handleAction = vi.fn();
        render(<EmptyLeads actionLabel="Create Lead" onAction={handleAction} />);

        const actionButton = screen.getByText('Create Lead');
        expect(actionButton).toBeInTheDocument();

        actionButton.click();
        expect(handleAction).toHaveBeenCalledTimes(1);
      });

      it('EmptyGoals accepts optional action props', () => {
        const handleAction = vi.fn();
        render(<EmptyGoals actionLabel="Set Goal" onAction={handleAction} />);

        const actionButton = screen.getByText('Set Goal');
        expect(actionButton).toBeInTheDocument();

        actionButton.click();
        expect(handleAction).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('SkeletonLoader Integration', () => {
    it('renders card variant correctly', () => {
      const { container } = render(<CardSkeleton />);
      const card = container.querySelector('.bg-\\[\\#161B2E\\]');
      expect(card).toBeInTheDocument();
      expect(card).toHaveClass('border', 'border-[#2A2F42]', 'rounded-xl');
    });

    it('renders list variant correctly', () => {
      const { container } = render(<ListSkeleton />);
      const item = container.querySelector('.bg-\\[\\#161B2E\\]');
      expect(item).toBeInTheDocument();
      expect(container.querySelector('.rounded-full')).toBeInTheDocument();
    });

    it('renders table variant correctly', () => {
      const { container } = render(
        <table>
          <tbody>
            <TableSkeleton />
          </tbody>
        </table>
      );
      const row = container.querySelector('tr');
      expect(row).toBeInTheDocument();
      expect(row).toHaveClass('border-b');
    });

    it('renders text variant correctly', () => {
      const { container } = render(<TextSkeleton />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      expect(lines.length).toBe(3);
    });

    it('SkeletonLoader renders all variants', () => {
      const { container: cardContainer } = render(<SkeletonLoader variant="card" />);
      expect(cardContainer.querySelector('.rounded-xl')).toBeInTheDocument();

      const { container: listContainer } = render(<SkeletonLoader variant="list" />);
      expect(listContainer.querySelector('.rounded-full')).toBeInTheDocument();

      const { container: textContainer } = render(<SkeletonLoader variant="text" />);
      expect(textContainer.querySelector('.space-y-2')).toBeInTheDocument();

      const { container: tableContainer } = render(
        <table>
          <tbody>
            <SkeletonLoader variant="table" />
          </tbody>
        </table>
      );
      expect(tableContainer.querySelector('tr')).toBeInTheDocument();
    });

    it('SkeletonLoader respects count prop', () => {
      const { container } = render(<SkeletonLoader variant="card" count={3} />);
      const cards = container.querySelectorAll('.bg-\\[\\#161B2E\\]');
      expect(cards.length).toBe(3);
    });

    it('LeadsSkeleton renders card view mode', () => {
      const { container } = render(<LeadsSkeleton viewMode="card" count={3} />);
      const grid = container.querySelector('.grid');
      expect(grid).toBeInTheDocument();
      expect(grid).toHaveClass('md:grid-cols-2', 'xl:grid-cols-3');
    });

    it('LeadsSkeleton renders table view mode', () => {
      render(<LeadsSkeleton viewMode="table" />);

      expect(screen.getByText('Company')).toBeInTheDocument();
      expect(screen.getByText('Health')).toBeInTheDocument();
      expect(screen.getByText('Stage')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Value')).toBeInTheDocument();
      expect(screen.getByText('Last Activity')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
    });

    it('all skeleton variants have animate-pulse class', () => {
      const { container } = render(
        <>
          <CardSkeleton />
          <ListSkeleton />
          <TextSkeleton />
        </>
      );

      const animatedElements = container.querySelectorAll('.animate-pulse');
      expect(animatedElements.length).toBeGreaterThan(0);
    });
  });

  describe('OfflineBanner Integration', () => {
    const originalOnLine = navigator.onLine;

    beforeEach(() => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: true,
      });
    });

    afterEach(() => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: originalOnLine,
      });
    });

    it('does not render when online', () => {
      render(<OfflineBanner />);

      const banner = screen.queryByRole('status');
      expect(banner).not.toBeInTheDocument();
    });

    it('renders when offline', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        const banner = screen.getByRole('status');
        expect(banner).toBeInTheDocument();
        expect(banner).toHaveAttribute('aria-label', 'You are currently offline');
      });
    });

    it('dismisses when connection restored', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });

      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: true,
      });
      window.dispatchEvent(new Event('online'));

      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      });
    });

    it('shows when going offline from online state', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: true,
      });

      render(<OfflineBanner />);

      expect(screen.queryByRole('status')).not.toBeInTheDocument();

      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });
      window.dispatchEvent(new Event('offline'));

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });

    it('dismisses when dismiss button clicked', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });

      const dismissButton = screen.getByRole('button', {
        name: /dismiss offline notification/i,
      });
      dismissButton.click();

      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      });
    });

    it('resets dismissed state when connection restored', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });

      const dismissButton = screen.getByRole('button', {
        name: /dismiss offline notification/i,
      });
      dismissButton.click();

      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      });

      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: true,
      });
      window.dispatchEvent(new Event('online'));

      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });
      window.dispatchEvent(new Event('offline'));

      await waitFor(() => {
        expect(screen.getByRole('status')).toBeInTheDocument();
      });
    });

    it('has aria-live attribute for screen readers', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        const banner = screen.getByRole('status');
        expect(banner).toHaveAttribute('aria-live', 'polite');
      });
    });
  });

  describe('Component Loading State Flow Integration', () => {
    it('handles loading -> empty state transition', async () => {
      const { rerender } = render(<AsyncComponent isLoading={true} data={null} />);

      // Should show skeleton
      expect(screen.queryByText('No leads yet')).not.toBeInTheDocument();
      expect(screen.queryByText('No error')).not.toBeInTheDocument();

      // Transition to empty state
      rerender(<AsyncComponent isLoading={false} data={null} />);

      expect(screen.getByText('No leads yet')).toBeInTheDocument();
      expect(screen.getByText(/ARIA can start finding prospects/)).toBeInTheDocument();
    });

    it('handles loading -> data state transition', async () => {
      const { rerender } = render(<AsyncComponent isLoading={true} data={null} />);

      expect(screen.queryByText('Sample Data')).not.toBeInTheDocument();

      rerender(<AsyncComponent isLoading={false} data="Sample Data" />);

      expect(screen.getByText('Sample Data')).toBeInTheDocument();
      expect(screen.queryByText('No leads yet')).not.toBeInTheDocument();
    });
  });

  describe('Error Recovery Flow Integration', () => {
    it('ErrorBoundary wraps async component that may fail', async () => {
      const FailingAsyncComponent = ({ shouldFail }: { shouldFail: boolean }) => {
        if (shouldFail) {
          throw new Error('Async operation failed');
        }
        return <div>Success</div>;
      };

      render(
        <ErrorBoundary>
          <FailingAsyncComponent shouldFail={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });

  describe('Accessibility Integration', () => {
    it('ErrorBoundary has accessible reload button', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const reloadButton = screen.getByText('Reload');
      expect(reloadButton).toHaveAttribute('aria-label', 'Reload the page');
    });

    it('EmptyState action buttons are accessible', () => {
      const handleAction = vi.fn();
      render(
        <EmptyState
          icon={() => <div>Icon</div>}
          title="Test"
          description="Test description"
          actionLabel="Perform Action"
          onAction={handleAction}
        />
      );

      const actionButton = screen.getByText('Perform Action');
      expect(actionButton.closest('button')).toBeInTheDocument();
    });

    it('OfflineBanner has proper ARIA attributes', async () => {
      Object.defineProperty(navigator, 'onLine', {
        writable: true,
        value: false,
      });

      render(<OfflineBanner />);

      await waitFor(() => {
        const banner = screen.getByRole('status');
        expect(banner).toHaveAttribute('aria-live', 'polite');
        expect(banner).toHaveAttribute('aria-label', 'You are currently offline');
      });
    });
  });
});
