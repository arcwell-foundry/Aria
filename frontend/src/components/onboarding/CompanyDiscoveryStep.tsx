import { useState } from "react";
import { Building2, Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  validateEmail,
  submitCompanyDiscovery,
} from "@/api/companyDiscovery";
import { EnrichmentProgress } from "@/components/onboarding/EnrichmentProgress";
import { checkCrossUser } from "@/api/onboarding";
import { CompanyMemoryDeltaConfirmation } from "./CompanyMemoryDeltaConfirmation";

interface CompanyDiscoveryStepProps {
  onComplete: (companyData: { company_name: string; website: string; email: string }) => void;
}

export function CompanyDiscoveryStep({ onComplete }: CompanyDiscoveryStepProps) {
  const [formData, setFormData] = useState({
    company_name: "",
    website: "",
    email: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [emailValidating, setEmailValidating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);

  // Extract domain from email for cross-user check
  const emailDomain = formData.email.trim().split("@")[1];

  // Check for cross-user data when domain is valid and email is not a personal domain
  const { data: crossUserData } = useQuery({
    queryKey: ["crossUser", emailDomain],
    queryFn: () => checkCrossUser(emailDomain),
    enabled: !!emailDomain && !errors.email && emailValidating === false,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
  });

  const clearFieldError = (fieldName: string) => {
    setErrors((prev) => {
      const newErrors = { ...prev };
      delete newErrors[fieldName];
      return newErrors;
    });
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear error for this field when user starts typing
    if (errors[name]) {
      clearFieldError(name);
    }
    // Clear gate error when user changes any field
    if (gateError) {
      setGateError(null);
    }
  };

  const handleEmailBlur = async () => {
    if (!formData.email) return;

    setEmailValidating(true);
    try {
      const result = await validateEmail(formData.email);
      if (!result.valid && result.reason) {
        setErrors((prev) => ({ ...prev, email: result.reason as string }));
      } else if (result.valid) {
        clearFieldError("email");
      }
    } catch {
      // Silently fail validation errors on blur
    } finally {
      setEmailValidating(false);
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.company_name.trim()) {
      newErrors.company_name = "Company name is required";
    }

    if (!formData.website.trim()) {
      newErrors.website = "Company website is required";
    } else if (!isValidUrl(formData.website)) {
      newErrors.website = "Please enter a valid URL (e.g., https://yourcompany.com)";
    }

    if (!formData.email.trim()) {
      newErrors.email = "Email is required";
    } else if (!isValidEmail(formData.email)) {
      newErrors.email = "Please enter a valid email address";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsSubmitting(true);
    try {
      const result = await submitCompanyDiscovery(formData);

      if (result.success) {
        setIsSubmitted(true);
      } else {
        // Handle different error types
        if (result.type === "email_validation") {
          setErrors({ email: result.error });
        } else if (result.type === "vertical_mismatch") {
          setGateError(result.message || result.error);
        }
      }
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
          Tell ARIA about your company
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          This is ARIA's first step in becoming your team's intelligence layer.
        </p>
      </div>

      {/* Gate Error Panel - shown when company fails life sciences check */}
      {gateError && (
        <div
          className="rounded-xl bg-primary border border-border px-5 py-4 w-full animate-in fade-in slide-in-from-top-2 duration-300"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-start gap-3">
            <Building2 size={20} strokeWidth={1.5} className="text-secondary shrink-0 mt-0.5" />
            <div className="flex flex-col gap-3">
              <p className="font-sans text-[15px] leading-relaxed text-content">
                {gateError}
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setGateError(null)}
                  className="font-sans text-[13px] font-medium text-interactive hover:text-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded px-2 py-1"
                >
                  Try a different email
                </button>
                <span className="text-border">•</span>
                <a
                  href="mailto:support@luminone.ai"
                  className="font-sans text-[13px] font-medium text-interactive hover:text-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded px-2 py-1"
                >
                  Think this is a mistake? Contact us
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Cross-User Memory Delta Confirmation */}
      {crossUserData?.exists && crossUserData.recommendation !== "full" && (
        <CompanyMemoryDeltaConfirmation
          data={crossUserData}
          showGaps={crossUserData.recommendation === "partial"}
        />
      )}

      {/* Form — hidden after successful submission */}
      {!isSubmitted && (
        <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
          {/* Company Name */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="company_name"
              className="font-sans text-[13px] font-medium text-secondary"
            >
              Company Name <span aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>
            <input
              type="text"
              id="company_name"
              name="company_name"
              value={formData.company_name}
              onChange={handleChange}
              disabled={isSubmitting}
              placeholder="e.g., Genentech"
              autoComplete="organization"
              className={`
                bg-white border rounded-lg px-4 py-3 text-[15px] font-sans
                focus:outline-none focus:ring-1 transition-colors duration-150
                disabled:opacity-50 disabled:cursor-not-allowed
                ${
                  errors.company_name
                    ? "border-critical focus:border-critical focus:ring-critical"
                    : "border-border focus:border-interactive focus:ring-interactive"
                }
              `}
              aria-invalid={errors.company_name ? "true" : "false"}
              aria-describedby={
                errors.company_name ? "company_name-error" : undefined
              }
            />
            {errors.company_name && (
              <p
                id="company_name-error"
                className="font-sans text-[13px] text-critical"
                role="alert"
                aria-live="polite"
              >
                {errors.company_name}
              </p>
            )}
          </div>

          {/* Website */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="website"
              className="font-sans text-[13px] font-medium text-secondary"
            >
              Company Website <span aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>
            <input
              type="url"
              id="website"
              name="website"
              value={formData.website}
              onChange={handleChange}
              disabled={isSubmitting}
              placeholder="https://yourcompany.com"
              autoComplete="organization url"
              className={`
                bg-white border rounded-lg px-4 py-3 text-[15px] font-sans
                focus:outline-none focus:ring-1 transition-colors duration-150
                disabled:opacity-50 disabled:cursor-not-allowed
                ${
                  errors.website
                    ? "border-critical focus:border-critical focus:ring-critical"
                    : "border-border focus:border-interactive focus:ring-interactive"
                }
              `}
              aria-invalid={errors.website ? "true" : "false"}
              aria-describedby={errors.website ? "website-error" : undefined}
            />
            {errors.website && (
              <p
                id="website-error"
                className="font-sans text-[13px] text-critical"
                role="alert"
                aria-live="polite"
              >
                {errors.website}
              </p>
            )}
          </div>

          {/* Corporate Email */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="email"
              className="font-sans text-[13px] font-medium text-secondary"
            >
              Corporate Email <span aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>
            <div className="relative">
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                onBlur={handleEmailBlur}
                disabled={isSubmitting || emailValidating}
                placeholder="you@yourcompany.com"
                autoComplete="email"
                className={`
                  bg-white border rounded-lg px-4 py-3 text-[15px] font-sans w-full pr-10
                  focus:outline-none focus:ring-1 transition-colors duration-150
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${
                    errors.email
                      ? "border-critical focus:border-critical focus:ring-critical"
                      : "border-border focus:border-interactive focus:ring-interactive"
                  }
                `}
                aria-invalid={errors.email ? "true" : "false"}
                aria-describedby={errors.email ? "email-error" : undefined}
              />
              {emailValidating && (
                <Loader2
                  size={16}
                  strokeWidth={1.5}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-secondary animate-spin"
                  aria-hidden="true"
                />
              )}
            </div>
            {errors.email && (
              <p
                id="email-error"
                className="font-sans text-[13px] text-critical"
                role="alert"
                aria-live="polite"
              >
                {errors.email}
              </p>
            )}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className={`
              bg-interactive text-white rounded-lg px-5 py-2.5
              font-sans font-medium text-[15px]
              hover:bg-interactive-hover active:bg-interactive-hover
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed
              cursor-pointer flex items-center justify-center gap-2
              min-h-[44px]
            `}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} strokeWidth={1.5} className="animate-spin" aria-hidden="true" />
                <span>ARIA is analyzing...</span>
              </>
            ) : (
              "Continue"
            )}
          </button>
        </form>
      )}

      {/* Enrichment progress — shown after successful submission */}
      {isSubmitted && (
        <div className="flex flex-col gap-8">
          <EnrichmentProgress companyName={formData.company_name} />

          {/* Continue button */}
          <button
            type="button"
            onClick={() => onComplete(formData)}
            className={`
              bg-interactive text-white rounded-lg px-5 py-2.5
              font-sans font-medium text-[15px]
              hover:bg-interactive-hover active:bg-interactive-hover
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
              cursor-pointer flex items-center justify-center gap-2
              min-h-[44px]
            `}
          >
            Continue to next step
          </button>
        </div>
      )}

      {/* ARIA presence text — only shown before submission */}
      {!isSubmitted && (
        <p className="font-sans text-[13px] leading-relaxed text-secondary italic">
          Once you continue, I'll start researching your company in the background —
          you don't need to wait for me.
        </p>
      )}
    </div>
  );
}

// Validation helpers

function isValidUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function isValidEmail(value: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(value);
}
