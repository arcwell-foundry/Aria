import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { HelpTooltip } from '../HelpTooltip';

describe('HelpTooltip', () => {
  describe('rendering', () => {
    it('renders help icon button', () => {
      render(<HelpTooltip content="Help content" />);

      const button = screen.getByRole('button');
      expect(button).toBeInTheDocument();
      expect(button).toHaveAttribute('aria-label', 'Get help');
    });

    it('renders with aria-describedby attribute', () => {
      render(<HelpTooltip content="Help content" />);

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-describedby', 'help-tooltip-content');
    });

    it('renders HelpCircle icon from lucide-react', () => {
      const { container } = render(<HelpTooltip content="Help content" />);

      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(
        <HelpTooltip content="Help content" className="custom-class" />
      );

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass('custom-class');
    });
  });

  describe('tooltip visibility', () => {
    it('shows tooltip on hover (mouseenter event)', () => {
      render(<HelpTooltip content="Help content here" />);

      const button = screen.getByRole('button');

      // Tooltip should not be visible initially
      expect(screen.queryByText('Help content here')).not.toBeInTheDocument();

      // Simulate mouseenter
      fireEvent.mouseEnter(button);

      // Tooltip should now be visible
      expect(screen.getByText('Help content here')).toBeInTheDocument();
    });

    it('hides tooltip on mouseleave', () => {
      render(<HelpTooltip content="Help content here" />);

      const button = screen.getByRole('button');

      // Show the tooltip
      fireEvent.mouseEnter(button);
      expect(screen.getByText('Help content here')).toBeInTheDocument();

      // Hide the tooltip
      fireEvent.mouseLeave(button);
      expect(screen.queryByText('Help content here')).not.toBeInTheDocument();
    });

    it('toggles tooltip on click', () => {
      render(<HelpTooltip content="Help content here" />);

      const button = screen.getByRole('button');

      // Click to show
      fireEvent.click(button);
      expect(screen.getByText('Help content here')).toBeInTheDocument();

      // Click again to hide
      fireEvent.click(button);
      expect(screen.queryByText('Help content here')).not.toBeInTheDocument();
    });
  });

  describe('tooltip content', () => {
    it('displays string content', () => {
      render(<HelpTooltip content="This is help text" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      expect(screen.getByText('This is help text')).toBeInTheDocument();
    });

    it('displays React node content', () => {
      const customContent = (
        <div>
          <strong>Bold help</strong>
          <p>Paragraph help</p>
        </div>
      );

      const { container } = render(<HelpTooltip content={customContent} />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      expect(screen.getByText('Bold help')).toBeInTheDocument();
      expect(screen.getByText('Paragraph help')).toBeInTheDocument();
    });
  });

  describe('tooltip positioning', () => {
    it('renders with top placement by default', () => {
      const { container } = render(<HelpTooltip content="Help" placement="top" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('bottom-full');
    });

    it('renders with bottom placement', () => {
      const { container } = render(<HelpTooltip content="Help" placement="bottom" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('top-full');
    });

    it('renders with left placement', () => {
      const { container } = render(<HelpTooltip content="Help" placement="left" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('right-full');
    });

    it('renders with right placement', () => {
      const { container } = render(<HelpTooltip content="Help" placement="right" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('left-full');
    });
  });

  describe('accessibility', () => {
    it('has proper ARIA attributes', () => {
      render(<HelpTooltip content="Help content" />);

      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-label', 'Get help');
      expect(button).toHaveAttribute('aria-describedby', 'help-tooltip-content');
    });

    it('tooltip has role="tooltip"', () => {
      const { container } = render(<HelpTooltip content="Help content" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toBeInTheDocument();
    });

    it('has proper id for tooltip content', () => {
      const { container } = render(<HelpTooltip content="Help content" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('#help-tooltip-content');
      expect(tooltip).toBeInTheDocument();
    });

    it('icon has aria-hidden attribute', () => {
      const { container } = render(<HelpTooltip content="Help content" />);

      const svg = container.querySelector('svg');
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    });
  });

  describe('ARIA Design System compliance', () => {
    it('uses correct icon color text-[#7B8EAA]', () => {
      const { container } = render(<HelpTooltip content="Help" />);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('text-[#7B8EAA]');
    });

    it('uses correct hover color text-[#A0A8B8]', () => {
      const { container } = render(<HelpTooltip content="Help" />);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('hover:text-[#A0A8B8]');
    });

    it('tooltip has correct background bg-white', () => {
      const { container } = render(<HelpTooltip content="Help" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('bg-white');
    });

    it('tooltip has correct border border-[#E2E0DC]', () => {
      const { container } = render(<HelpTooltip content="Help" />);

      const button = screen.getByRole('button');
      fireEvent.mouseEnter(button);

      const tooltip = container.querySelector('[role="tooltip"]');
      expect(tooltip).toHaveClass('border-[#E2E0DC]');
    });

    it('has focus ring styling', () => {
      const { container } = render(<HelpTooltip content="Help" />);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('focus:ring-2', 'focus:ring-[#7B8EAA]');
    });
  });
});
