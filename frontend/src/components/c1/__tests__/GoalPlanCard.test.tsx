import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GoalPlanCard } from '../GoalPlanCard';

// Mock useOnAction
vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('GoalPlanCard', () => {
  const defaultProps = {
    goal_name: 'Test Goal',
    goal_id: 'goal-123',
    description: 'A test goal description',
    steps: [
      { step_number: 1, description: 'First step', status: 'pending' as const },
      { step_number: 2, description: 'Second step', status: 'in_progress' as const, assigned_agent: 'Hunter' },
    ],
  };

  it('renders goal name and description', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('Test Goal')).toBeInTheDocument();
    expect(screen.getByText('A test goal description')).toBeInTheDocument();
  });

  it('renders all steps', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('First step')).toBeInTheDocument();
    expect(screen.getByText('Second step')).toBeInTheDocument();
  });

  it('renders agent badges', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByText('Hunter')).toBeInTheDocument();
  });

  it('renders OODA phase badge when provided', () => {
    render(<GoalPlanCard {...defaultProps} ooda_phase="observe" />);
    expect(screen.getByText('observe')).toBeInTheDocument();
  });

  it('renders estimated duration when provided', () => {
    render(<GoalPlanCard {...defaultProps} estimated_duration="2 hours" />);
    expect(screen.getByText('2 hours')).toBeInTheDocument();
  });

  it('renders Approve and Modify buttons', () => {
    render(<GoalPlanCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /modify/i })).toBeInTheDocument();
  });

  it('handles empty steps array', () => {
    render(<GoalPlanCard {...defaultProps} steps={[]} />);
    expect(screen.getByText('Test Goal')).toBeInTheDocument();
  });

  it('handles minimal props', () => {
    render(
      <GoalPlanCard
        goal_name="Minimal"
        goal_id="id-1"
        description="Desc"
        steps={[]}
      />
    );
    expect(screen.getByText('Minimal')).toBeInTheDocument();
  });
});
