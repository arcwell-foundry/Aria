import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitResponseFeedback } from "@/api/feedback";

interface FeedbackWidgetProps {
  messageId: string;
  className?: string;
}

export function FeedbackWidget({ messageId, className = "" }: FeedbackWidgetProps) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleThumbsUp = async () => {
    if (submitted || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await submitResponseFeedback({
        message_id: messageId,
        rating: "up",
      });
      setRating("up");
      setSubmitted(true);
    } catch (error) {
      console.error("Failed to submit feedback:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleThumbsDown = () => {
    if (submitted || isSubmitting) return;
    setRating("down");
    setShowComment(true);
  };

  const handleSubmitComment = async () => {
    if (!comment.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await submitResponseFeedback({
        message_id: messageId,
        rating: "down",
        comment: comment.trim(),
      });
      setSubmitted(true);
    } catch (error) {
      console.error("Failed to submit feedback:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {!submitted && (
        <>
          <button
            onClick={handleThumbsUp}
            disabled={isSubmitting || rating === "down"}
            className="p-1.5 text-slate-400 hover:text-success hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="This was helpful"
          >
            <ThumbsUp className="w-4 h-4" />
          </button>
          <button
            onClick={handleThumbsDown}
            disabled={isSubmitting || rating === "up"}
            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="This needs improvement"
          >
            <ThumbsDown className="w-4 h-4" />
          </button>
        </>
      )}

      {submitted && rating === "up" && (
        <span className="text-sm text-success">Thanks!</span>
      )}

      {showComment && !submitted && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Tell us more..."
            className="px-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            disabled={isSubmitting}
            autoFocus
          />
          <button
            onClick={handleSubmitComment}
            disabled={!comment.trim() || isSubmitting}
            className="px-3 py-1.5 text-sm font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSubmitting ? "Sending..." : "Send"}
          </button>
        </div>
      )}

      {submitted && rating === "down" && (
        <span className="text-sm text-slate-400">Thanks for your feedback</span>
      )}
    </div>
  );
}
