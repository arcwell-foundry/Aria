import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { OnboardingTooltip } from '../OnboardingTooltip';

describe('OnboardingTooltip', () => {
  describe('rendering', () => {
    it('renders tooltip when not dismissed', () => {
      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      expect(screen.getByText('Welcome')).toBeInTheDocument();
      expect(screen.getByText('Get started with ARIA')).toBeInTheDocument();
      expect(screen.getByText('Target Element')).toBeInTheDocument();
    });

    it('does not render when initiallyDismissed is true', () => {
      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
          initiallyDismissed={true}
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      expect(screen.queryByText('Welcome')).not.toBeInTheDocument();
      expect(screen.queryByText('Get started with ARIA')).not.toBeInTheDocument();
      expect(screen.getByText('Target Element')).toBeInTheDocument();
    });

    it('renders dismiss button (X icon)', () => {
      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      expect(dismissButton).toBeInTheDocument();

      // Should have X icon from lucide-react
      const { container } = render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
          className="custom-class"
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass('custom-class');
    });
  });

  describe('dismiss behavior', () => {
    it('calls onDismiss when dismissed', () => {
      const onDismiss = vi.fn();

      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
          onDismiss={onDismiss}
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      fireEvent.click(dismissButton);

      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it('hides tooltip after dismissal', () => {
      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
        >
          <button>Target Element</button>
        </OnboardingTooltip>
      );

      expect(screen.getByText('Welcome')).toBeInTheDocument();

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      fireEvent.click(dismissButton);

      expect(screen.queryByText('Welcome')).not.toBeInTheDocument();
      expect(screen.queryByText('Get started with ARIA')).not.toBeInTheDocument();
    });

    it('only renders children after dismissal', () => {
      render(
        <OnboardingTooltip
          title="Welcome"
          content="Get started with ARIA"
        >
          <button data-testid="target">Target Element</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      fireEvent.click(dismissButton);

      // Children should still be rendered
      expect(screen.getByTestId('target')).toBeInTheDocument();

      // Tooltip content should be gone
      expect(screen.queryByText('Welcome')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Dismiss tooltip' })).not.toBeInTheDocument();
    });
  });

  describe('content rendering', () => {
    it('renders string content', () => {
      render(
        <OnboardingTooltip
          title="Feature Title"
          content="This is the tooltip content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      expect(screen.getByText('This is the tooltip content')).toBeInTheDocument();
    });

    it('renders React node content', () => {
      const customContent = (
        <div>
          <strong>Strong text</strong>
          <p>Paragraph content</p>
        </div>
      );

      render(
        <OnboardingTooltip
          title="Feature Title"
          content={customContent}
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      expect(screen.getByText('Strong text')).toBeInTheDocument();
      expect(screen.getByText('Paragraph content')).toBeInTheDocument();
    });

    it('renders title as h3', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Feature Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const heading = container.querySelector('h3');
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveTextContent('Feature Title');
    });
  });

  describe('tooltip positioning', () => {
    it('renders with top placement by default', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
          placement="top"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('bottom-full');
    });

    it('renders with bottom placement', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
          placement="bottom"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('top-full');
    });

    it('renders with left placement', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
          placement="left"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('right-full');
    });

    it('renders with right placement', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
          placement="right"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('left-full');
    });
  });

  describe('accessibility', () => {
    it('has proper ARIA attributes', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Tooltip Title"
          content="Tooltip content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveAttribute('aria-labelledby', 'onboarding-tooltip-title');
      expect(tooltip).toHaveAttribute('aria-describedby', 'onboarding-tooltip-content');
    });

    it('dismiss button has proper aria-label', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      expect(dismissButton).toBeInTheDocument();
    });

    it('has proper id attributes for title and content', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      expect(container.querySelector('#onboarding-tooltip-title')).toBeInTheDocument();
      expect(container.querySelector('#onboarding-tooltip-content')).toBeInTheDocument();
    });

    it('X icon has aria-hidden attribute', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const svg = container.querySelector('svg');
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    });

    it('dismiss button has focus ring styling', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      expect(dismissButton).toHaveClass('focus:ring-2', 'focus:ring-[#7B8EAA]');
    });
  });

  describe('ARIA Design System compliance', () => {
    it('uses correct background bg-white', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('bg-white');
    });

    it('uses correct border border-[#E2E0DC]', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('border-[#E2E0DC]');
    });

    it('uses correct shadow shadow-sm', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]');
      expect(tooltip).toHaveClass('shadow-sm');
    });

    it('has border between header and content', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const header = container.querySelector('.border-b');
      expect(header).toBeInTheDocument();
      expect(header).toHaveClass('border-[#E2E0DC]');
    });

    it('dismiss button uses correct colors', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      expect(dismissButton).toHaveClass('text-[#7B8EAA]', 'hover:text-[#1A1A1A]');
    });

    it('uses Satoshi font family', () => {
      const { container } = render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <button>Target</button>
        </OnboardingTooltip>
      );

      const tooltip = container.querySelector('[role="dialog"]') as HTMLElement;
      expect(tooltip.style.fontFamily).toContain('Satoshi');
    });
  });

  describe('children rendering', () => {
    it('renders children unchanged when tooltip is visible', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <div data-testid="child" className="child-class">
            Child Content
          </div>
        </OnboardingTooltip>
      );

      const child = screen.getByTestId('child');
      expect(child).toBeInTheDocument();
      expect(child).toHaveClass('child-class');
      expect(child).toHaveTextContent('Child Content');
    });

    it('renders children unchanged after dismissal', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <div data-testid="child" className="child-class">
            Child Content
          </div>
        </OnboardingTooltip>
      );

      const dismissButton = screen.getByRole('button', { name: 'Dismiss tooltip' });
      fireEvent.click(dismissButton);

      const child = screen.getByTestId('child');
      expect(child).toBeInTheDocument();
      expect(child).toHaveClass('child-class');
      expect(child).toHaveTextContent('Child Content');
    });

    it('handles multiple children', () => {
      render(
        <OnboardingTooltip
          title="Title"
          content="Content"
        >
          <>
            <button>First Child</button>
            <button>Second Child</button>
          </>
        </OnboardingTooltip>
      );

      expect(screen.getByText('First Child')).toBeInTheDocument();
      expect(screen.getByText('Second Child')).toBeInTheDocument();
    });
  });
});
