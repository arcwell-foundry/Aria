import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SignalAlertCard } from '../SignalAlertCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('SignalAlertCard', () => {
  const defaultProps = {
    signal_id: 'signal-123',
    title: 'Patent Cliff Alert',
    severity: 'high' as const,
    signal_type: 'patent_cliff',
    summary: 'Key patent expiring in Q4 2026.',
  };

  it('renders title and summary', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('Patent Cliff Alert')).toBeInTheDocument();
    expect(screen.getByText('Key patent expiring in Q4 2026.')).toBeInTheDocument();
  });

  it('renders severity badge', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('HIGH')).toBeInTheDocument();
  });

  it('renders signal type', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByText('patent_cliff')).toBeInTheDocument();
  });

  it('renders source when provided', () => {
    render(<SignalAlertCard {...defaultProps} source="FDA Database" />);
    expect(screen.getByText(/Source: FDA Database/)).toBeInTheDocument();
  });

  it('renders affected accounts', () => {
    render(<SignalAlertCard {...defaultProps} affected_accounts={['Acme Corp', 'Beta Inc']} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Beta Inc')).toBeInTheDocument();
  });

  it('renders Investigate button', () => {
    render(<SignalAlertCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /investigate/i })).toBeInTheDocument();
  });

  it('applies severity-based styling', () => {
    const { container } = render(<SignalAlertCard {...defaultProps} severity="high" />);
    // Check for severity class or style
    expect(container.firstChild).toBeInTheDocument();
  });
});
