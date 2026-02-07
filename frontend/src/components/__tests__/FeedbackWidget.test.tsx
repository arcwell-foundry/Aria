import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FeedbackWidget } from '../FeedbackWidget';
import * as feedbackApi from '@/api/feedback';

// Mock the feedback API
vi.mock('@/api/feedback', () => ({
  submitResponseFeedback: vi.fn(),
}));

describe('FeedbackWidget', () => {
  const mockMessageId = 'test-message-123';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders thumbs up and thumbs down buttons', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      const thumbsDownButton = screen.getByTitle('This needs improvement');

      expect(thumbsUpButton).toBeInTheDocument();
      expect(thumbsDownButton).toBeInTheDocument();
    });

    it('renders with custom className', () => {
      const { container } = render(
        <FeedbackWidget messageId={mockMessageId} className="custom-class" />
      );

      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass('custom-class');
    });

    it('disables buttons when submitted', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(thumbsUpButton).toBeDisabled();
      });
    });
  });

  describe('thumbs up feedback', () => {
    it('shows thanks message after positive feedback', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(screen.getByText('Thanks!')).toBeInTheDocument();
      });
    });

    it('calls submitResponseFeedback API with correct data', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalledWith({
          message_id: mockMessageId,
          rating: 'up',
        });
      });
    });

    it('hides feedback buttons after submission', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(screen.queryByTitle('This was helpful')).not.toBeInTheDocument();
        expect(screen.queryByTitle('This needs improvement')).not.toBeInTheDocument();
      });
    });
  });

  describe('thumbs down feedback', () => {
    it('expands comment field on thumbs down', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      expect(screen.getByPlaceholderText('Tell us more...')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
    });

    it('does not disable thumbs down button after clicking (allows re-selection)', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      // Thumbs down button remains enabled because clicking it again is allowed
      expect(thumbsDownButton).not.toBeDisabled();
    });

    it('disables thumbs up button after thumbs down click', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      expect(thumbsUpButton).toBeDisabled();
    });

    it('submits comment when Send button is clicked', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      // Click thumbs down
      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      // Type comment
      const input = screen.getByPlaceholderText('Tell us more...');
      fireEvent.change(input, { target: { value: 'This response was not helpful' } });

      // Submit
      const sendButton = screen.getByRole('button', { name: 'Send' });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalledWith({
          message_id: mockMessageId,
          rating: 'down',
          comment: 'This response was not helpful',
        });
      });
    });

    it('shows thanks message after comment submission', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      // Click thumbs down
      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      // Type and submit comment
      const input = screen.getByPlaceholderText('Tell us more...');
      fireEvent.change(input, { target: { value: 'Feedback comment' } });

      const sendButton = screen.getByRole('button', { name: 'Send' });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByText('Thanks for your feedback')).toBeInTheDocument();
      });
    });

    it('disables send button when comment is empty', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      const sendButton = screen.getByRole('button', { name: 'Send' });
      expect(sendButton).toBeDisabled();
    });

    it('enables send button when comment has text', () => {
      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      const input = screen.getByPlaceholderText('Tell us more...');
      fireEvent.change(input, { target: { value: 'Some feedback' } });

      const sendButton = screen.getByRole('button', { name: 'Send' });
      expect(sendButton).not.toBeDisabled();
    });

    it('trims whitespace from comment before submission', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockResolvedValue({
        message: 'Feedback received',
        feedback_id: 'feedback-123',
      });

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      const input = screen.getByPlaceholderText('Tell us more...');
      fireEvent.change(input, { target: { value: '  feedback with spaces  ' } });

      const sendButton = screen.getByRole('button', { name: 'Send' });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalledWith({
          message_id: mockMessageId,
          rating: 'down',
          comment: 'feedback with spaces',
        });
      });
    });
  });

  describe('interaction states', () => {
    it('prevents multiple submissions while submitting', async () => {
      let resolveSubmit: (value: any) => void;
      const submitPromise = new Promise((resolve) => {
        resolveSubmit = resolve;
      });

      vi.mocked(feedbackApi.submitResponseFeedback).mockReturnValue(submitPromise as any);

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      // Should be disabled immediately
      expect(thumbsUpButton).toBeDisabled();

      // Try clicking again
      fireEvent.click(thumbsUpButton);

      // Should still only have one call
      expect(feedbackApi.submitResponseFeedback).toHaveBeenCalledTimes(1);

      // Resolve the promise
      resolveSubmit!({ message: 'Feedback received', feedback_id: 'feedback-123' });

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalled();
      });
    });

    it('shows "Sending..." text while submitting', async () => {
      let resolveSubmit: (value: any) => void;
      const submitPromise = new Promise((resolve) => {
        resolveSubmit = resolve;
      });

      vi.mocked(feedbackApi.submitResponseFeedback).mockReturnValue(submitPromise as any);

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      fireEvent.click(thumbsDownButton);

      const input = screen.getByPlaceholderText('Tell us more...');
      fireEvent.change(input, { target: { value: 'Test feedback' } });

      const sendButton = screen.getByRole('button', { name: 'Send' });
      fireEvent.click(sendButton);

      // Should show "Sending..."
      await waitFor(() => {
        expect(sendButton).toHaveTextContent('Sending...');
      });

      // Resolve the promise
      resolveSubmit!({ message: 'Feedback received', feedback_id: 'feedback-123' });
    });
  });

  describe('error handling', () => {
    it('handles API errors gracefully', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockRejectedValue(
        new Error('API Error')
      );

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalled();
      });

      // Should log error but not crash
      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to submit feedback:',
        expect.any(Error)
      );

      consoleSpy.mockRestore();
    });

    it('re-enables buttons after failed submission', async () => {
      vi.mocked(feedbackApi.submitResponseFeedback).mockRejectedValue(
        new Error('API Error')
      );

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      fireEvent.click(thumbsUpButton);

      await waitFor(() => {
        expect(feedbackApi.submitResponseFeedback).toHaveBeenCalled();
      });

      // Button should be re-enabled after error
      expect(thumbsUpButton).not.toBeDisabled();

      consoleSpy.mockRestore();
    });
  });

  describe('icon rendering', () => {
    it('renders ThumbsUp and ThumbsDown icons from lucide-react', () => {
      const { container } = render(<FeedbackWidget messageId={mockMessageId} />);

      const svgs = container.querySelectorAll('svg');
      expect(svgs.length).toBe(2); // Two icons
    });
  });

  describe('styling', () => {
    it('thumbs up has correct hover classes', () => {
      const { container } = render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsUpButton = screen.getByTitle('This was helpful');
      expect(thumbsUpButton).toHaveClass('hover:text-emerald-400', 'hover:bg-slate-800');
    });

    it('thumbs down has correct hover classes', () => {
      const { container } = render(<FeedbackWidget messageId={mockMessageId} />);

      const thumbsDownButton = screen.getByTitle('This needs improvement');
      expect(thumbsDownButton).toHaveClass('hover:text-rose-400', 'hover:bg-slate-800');
    });
  });
});
