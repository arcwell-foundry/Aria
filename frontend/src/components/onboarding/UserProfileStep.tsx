import { useState } from "react";
import { Loader2 } from "lucide-react";
import { updateUserDetails } from "@/api/profile";

interface UserProfileStepProps {
  onComplete: () => void;
  onSkip?: () => void;
}

export function UserProfileStep({ onComplete, onSkip }: UserProfileStepProps) {
  const [formData, setFormData] = useState({
    full_name: "",
    title: "",
    department: "",
    linkedin_url: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.full_name.trim()) {
      newErrors.full_name = "Full name is required";
    }

    if (!formData.title.trim()) {
      newErrors.title = "Job title is required";
    }

    if (
      formData.linkedin_url.trim() &&
      !formData.linkedin_url.startsWith("https://linkedin.com/") &&
      !formData.linkedin_url.startsWith("https://www.linkedin.com/")
    ) {
      newErrors.linkedin_url =
        "Please enter a valid LinkedIn URL (https://www.linkedin.com/...)";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsSubmitting(true);
    try {
      const payload: Record<string, string> = {
        full_name: formData.full_name.trim(),
        title: formData.title.trim(),
      };
      if (formData.department.trim()) {
        payload.department = formData.department.trim();
      }
      if (formData.linkedin_url.trim()) {
        payload.linkedin_url = formData.linkedin_url.trim();
      }

      await updateUserDetails(payload);
      onComplete();
    } catch {
      setErrors({
        _form: "Something went wrong. Please try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-8 max-w-md animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-content font-display">
          Tell ARIA about yourself
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          ARIA uses your role and context to prioritize what matters most to you.
        </p>
      </div>

      {/* ARIA note */}
      <div className="rounded-xl bg-subtle border border-border px-5 py-4 w-full">
        <p className="font-sans text-[13px] leading-relaxed text-secondary italic">
          I'll calibrate how I communicate and prioritize based on your working style.
        </p>
      </div>

      {/* Form error */}
      {errors._form && (
        <p className="font-sans text-[13px] text-critical" role="alert">
          {errors._form}
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        {/* Full Name */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="full_name"
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Full Name <span aria-hidden="true">*</span>
            <span className="sr-only">(required)</span>
          </label>
          <input
            type="text"
            id="full_name"
            name="full_name"
            value={formData.full_name}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="e.g., Jane Chen"
            autoComplete="name"
            className={`
              bg-white border rounded-lg px-4 py-3 text-[15px] font-sans
              focus:outline-none focus:ring-1 transition-colors duration-150
              disabled:opacity-50 disabled:cursor-not-allowed
              ${
                errors.full_name
                  ? "border-critical focus:border-critical focus:ring-critical"
                  : "border-border focus:border-interactive focus:ring-interactive"
              }
            `}
            aria-invalid={errors.full_name ? "true" : "false"}
            aria-describedby={errors.full_name ? "full_name-error" : undefined}
          />
          {errors.full_name && (
            <p
              id="full_name-error"
              className="font-sans text-[13px] text-critical"
              role="alert"
              aria-live="polite"
            >
              {errors.full_name}
            </p>
          )}
        </div>

        {/* Job Title */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="title"
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Job Title <span aria-hidden="true">*</span>
            <span className="sr-only">(required)</span>
          </label>
          <input
            type="text"
            id="title"
            name="title"
            value={formData.title}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="e.g., Regional Sales Director"
            autoComplete="organization-title"
            className={`
              bg-white border rounded-lg px-4 py-3 text-[15px] font-sans
              focus:outline-none focus:ring-1 transition-colors duration-150
              disabled:opacity-50 disabled:cursor-not-allowed
              ${
                errors.title
                  ? "border-critical focus:border-critical focus:ring-critical"
                  : "border-border focus:border-interactive focus:ring-interactive"
              }
            `}
            aria-invalid={errors.title ? "true" : "false"}
            aria-describedby={errors.title ? "title-error" : undefined}
          />
          {errors.title && (
            <p
              id="title-error"
              className="font-sans text-[13px] text-critical"
              role="alert"
              aria-live="polite"
            >
              {errors.title}
            </p>
          )}
        </div>

        {/* Department */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="department"
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Department
          </label>
          <input
            type="text"
            id="department"
            name="department"
            value={formData.department}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="e.g., Commercial Operations"
            autoComplete="off"
            className="
              bg-white border border-border rounded-lg px-4 py-3 text-[15px] font-sans
              focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive
              transition-colors duration-150
              disabled:opacity-50 disabled:cursor-not-allowed
            "
          />
        </div>

        {/* LinkedIn URL */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="linkedin_url"
            className="font-sans text-[13px] font-medium text-secondary"
          >
            LinkedIn URL{" "}
            <span className="text-tertiary font-normal">(optional)</span>
          </label>
          <input
            type="url"
            id="linkedin_url"
            name="linkedin_url"
            value={formData.linkedin_url}
            onChange={handleChange}
            disabled={isSubmitting}
            placeholder="https://www.linkedin.com/in/yourprofile"
            autoComplete="off"
            className={`
              bg-white border rounded-lg px-4 py-3 text-[15px] font-sans
              focus:outline-none focus:ring-1 transition-colors duration-150
              disabled:opacity-50 disabled:cursor-not-allowed
              ${
                errors.linkedin_url
                  ? "border-critical focus:border-critical focus:ring-critical"
                  : "border-border focus:border-interactive focus:ring-interactive"
              }
            `}
            aria-invalid={errors.linkedin_url ? "true" : "false"}
            aria-describedby={
              errors.linkedin_url ? "linkedin_url-error" : undefined
            }
          />
          {errors.linkedin_url && (
            <p
              id="linkedin_url-error"
              className="font-sans text-[13px] text-critical"
              role="alert"
              aria-live="polite"
            >
              {errors.linkedin_url}
            </p>
          )}
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isSubmitting}
            className="
              bg-interactive text-white rounded-lg px-5 py-2.5
              font-sans font-medium text-[15px]
              hover:bg-interactive-hover active:bg-interactive-hover
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed
              cursor-pointer flex items-center justify-center gap-2
              min-h-[44px]
            "
          >
            {isSubmitting ? (
              <>
                <Loader2
                  size={16}
                  strokeWidth={1.5}
                  className="animate-spin"
                  aria-hidden="true"
                />
                <span>Saving...</span>
              </>
            ) : (
              "Continue"
            )}
          </button>

          {onSkip && (
            <button
              type="button"
              onClick={onSkip}
              disabled={isSubmitting}
              className="
                bg-transparent text-secondary rounded-lg px-4 py-2.5
                font-sans text-[15px]
                hover:bg-subtle
                transition-colors duration-150
                focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
                disabled:opacity-50 disabled:cursor-not-allowed
                cursor-pointer
              "
            >
              Skip for now
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
