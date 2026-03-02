import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentStatusCard } from '../AgentStatusCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('AgentStatusCard', () => {
  const defaultProps = {
    agents: [
      { name: 'Hunter', status: 'working' as const, current_task: 'Searching leads' },
      { name: 'Scribe', status: 'idle' as const },
    ],
  };

  it('renders agent names', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('Hunter')).toBeInTheDocument();
    expect(screen.getByText('Scribe')).toBeInTheDocument();
  });

  it('renders current task', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('Searching leads')).toBeInTheDocument();
  });

  it('renders OODA phase', () => {
    render(<AgentStatusCard {...defaultProps} agents={[{ name: 'Hunter', status: 'working', ooda_phase: 'observe' }]} />);
    expect(screen.getByText('observe')).toBeInTheDocument();
  });

  it('shows active agent count', () => {
    render(<AgentStatusCard {...defaultProps} />);
    expect(screen.getByText('1 active')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    render(<AgentStatusCard agents={[]} />);
    expect(screen.getByText('No agents currently active')).toBeInTheDocument();
  });

  it('handles agents with progress', () => {
    render(<AgentStatusCard agents={[{ name: 'Hunter', status: 'working', progress: 50 }]} />);
    // Progress bar should be rendered
    expect(screen.getByText('Hunter')).toBeInTheDocument();
  });
});
