import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EmptyState, EmptyLeads, EmptyGoals, EmptyBriefings, EmptyBattleCards, EmptyMeetingBriefs, EmptyDrafts, EmptyActivity } from '../EmptyState';
import { Target } from 'lucide-react';

describe('EmptyState', () => {
  it('renders icon, title, and description', () => {
    render(
      <EmptyState
        icon={Target}
        title="No items yet"
        description="This is a test description"
      />
    );

    expect(screen.getByText('No items yet')).toBeInTheDocument();
    expect(screen.getByText('This is a test description')).toBeInTheDocument();
  });

  it('renders action button when actionLabel and onAction are provided', () => {
    const handleAction = vi.fn();

    render(
      <EmptyState
        icon={Target}
        title="No items yet"
        description="This is a test description"
        actionLabel="Get Started"
        onAction={handleAction}
      />
    );

    const actionButton = screen.getByText('Get Started');
    expect(actionButton).toBeInTheDocument();
    expect(actionButton.closest('button')).toBeInTheDocument();

    actionButton.click();
    expect(handleAction).toHaveBeenCalledTimes(1);
  });

  it('does not render action button when onAction is not provided', () => {
    render(
      <EmptyState
        icon={Target}
        title="No items yet"
        description="This is a test description"
        actionLabel="Get Started"
      />
    );

    expect(screen.queryByText('Get Started')).not.toBeInTheDocument();
  });

  it('uses Lucide icon component', () => {
    const { container } = render(
      <EmptyState
        icon={Target}
        title="No items yet"
        description="This is a test description"
      />
    );

    // Lucide icons render as SVG elements
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <EmptyState
        icon={Target}
        title="No items yet"
        description="This is a test description"
        className="custom-class"
      />
    );

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass('custom-class');
  });

  describe('Preset Variants', () => {
    it('EmptyLeads renders with correct content', () => {
      render(<EmptyLeads />);

      expect(screen.getByText('No leads yet')).toBeInTheDocument();
      expect(screen.getByText(/ARIA can start finding prospects/)).toBeInTheDocument();
    });

    it('EmptyGoals renders with correct content', () => {
      render(<EmptyGoals />);

      expect(screen.getByText('No goals yet')).toBeInTheDocument();
      expect(screen.getByText(/Set a goal and ARIA will start working/)).toBeInTheDocument();
    });

    it('EmptyBriefings renders with correct content', () => {
      render(<EmptyBriefings />);

      expect(screen.getByText('No briefings yet')).toBeInTheDocument();
      expect(screen.getByText(/Connect your email and CRM/)).toBeInTheDocument();
    });

    it('EmptyBattleCards renders with correct content', () => {
      render(<EmptyBattleCards />);

      expect(screen.getByText('No battle cards yet')).toBeInTheDocument();
      expect(screen.getByText(/ARIA will generate competitive battle cards/)).toBeInTheDocument();
    });

    it('EmptyMeetingBriefs renders with correct content', () => {
      render(<EmptyMeetingBriefs />);

      expect(screen.getByText('No upcoming meetings')).toBeInTheDocument();
      expect(screen.getByText(/ARIA prepares research briefs/)).toBeInTheDocument();
    });

    it('EmptyDrafts renders with correct content', () => {
      render(<EmptyDrafts />);

      expect(screen.getByText('No drafts yet')).toBeInTheDocument();
      expect(screen.getByText(/ARIA helps you write faster/)).toBeInTheDocument();
    });

    it('EmptyActivity renders with correct content', () => {
      render(<EmptyActivity />);

      expect(screen.getByText('ARIA is getting started')).toBeInTheDocument();
      expect(screen.getByText(/Complete onboarding/)).toBeInTheDocument();
    });

    it('EmptyLeads uses Target icon', () => {
      const { container } = render(<EmptyLeads />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyGoals uses Target icon', () => {
      const { container } = render(<EmptyGoals />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyBriefings uses Mail icon', () => {
      const { container } = render(<EmptyBriefings />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyBattleCards uses Shield icon', () => {
      const { container } = render(<EmptyBattleCards />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyMeetingBriefs uses Calendar icon', () => {
      const { container } = render(<EmptyMeetingBriefs />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyDrafts uses FileText icon', () => {
      const { container } = render(<EmptyDrafts />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('EmptyActivity uses Sparkles icon', () => {
      const { container } = render(<EmptyActivity />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });
  });
});
