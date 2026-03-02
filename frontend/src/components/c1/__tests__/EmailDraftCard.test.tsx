import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmailDraftCard } from '../EmailDraftCard';

vi.mock('@thesysai/genui-sdk', () => ({
  useOnAction: () => vi.fn(),
}));

describe('EmailDraftCard', () => {
  const defaultProps = {
    email_draft_id: 'draft-123',
    to: 'test@example.com',
    subject: 'Test Subject',
    body: 'This is the email body content.',
    tone: 'neutral' as const,
  };

  it('renders recipient and subject', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByText('test@example.com')).toBeInTheDocument();
    expect(screen.getByText('Test Subject')).toBeInTheDocument();
  });

  it('renders body content', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByText(/This is the email body/)).toBeInTheDocument();
  });

  it('renders tone badge', () => {
    render(<EmailDraftCard {...defaultProps} tone="formal" />);
    expect(screen.getByText('formal')).toBeInTheDocument();
  });

  it('renders context when provided', () => {
    render(<EmailDraftCard {...defaultProps} context="Drafted in response to inquiry" />);
    expect(screen.getByText('Drafted in response to inquiry')).toBeInTheDocument();
  });

  it('renders action buttons', () => {
    render(<EmailDraftCard {...defaultProps} />);
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('truncates long body content', () => {
    const longBody = 'A'.repeat(300);
    render(<EmailDraftCard {...defaultProps} body={longBody} />);
    expect(screen.getByText(/A+\.\.\./)).toBeInTheDocument();
  });
});
