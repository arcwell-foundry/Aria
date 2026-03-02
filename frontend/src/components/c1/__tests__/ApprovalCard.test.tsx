import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ApprovalCard } from '../ApprovalCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('ApprovalCard', () => {
  const defaultProps = {
    item_id: 'item-123',
    item_type: 'task',
    title: 'Approve CRM Sync',
    description: 'Allow ARIA to sync with Salesforce.',
  };

  it('renders title and description', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByText('Approve CRM Sync')).toBeInTheDocument();
    expect(screen.getByText('Allow ARIA to sync with Salesforce.')).toBeInTheDocument();
  });

  it('renders item type', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByText('task')).toBeInTheDocument();
  });

  it('renders impact when provided', () => {
    render(<ApprovalCard {...defaultProps} impact="This will enable automatic lead imports" />);
    expect(screen.getByText('This will enable automatic lead imports')).toBeInTheDocument();
  });

  it('renders urgency badge for non-default urgency', () => {
    render(<ApprovalCard {...defaultProps} urgency="immediate" />);
    expect(screen.getByText('Immediate')).toBeInTheDocument();
  });

  it('does not render urgency badge for no_rush', () => {
    render(<ApprovalCard {...defaultProps} urgency="no_rush" />);
    expect(screen.queryByText('No Rush')).not.toBeInTheDocument();
  });

  it('renders Approve and Reject buttons', () => {
    render(<ApprovalCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });
});
