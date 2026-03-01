import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { signup } = useAuth();
  const navigate = useNavigate();

  const validatePassword = (pass: string): string | null => {
    if (pass.length < 8) {
      return 'Password must be at least 8 characters';
    }
    if (!/[A-Z]/.test(pass)) {
      return 'Password must contain at least one uppercase letter';
    }
    if (!/[0-9]/.test(pass)) {
      return 'Password must contain at least one number';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validate password
    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    // Check password match
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setIsLoading(true);

    const signupPayload = {
      email,
      password,
      full_name: fullName,
      company_name: companyName || undefined,
    };

    try {
      await signup(signupPayload);
      navigate('/onboarding');
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to create account');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0A0A0B] via-[#0F1117] to-[#0A0A0B] flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-display italic text-white mb-2">ARIA</h1>
          <p className="text-[#8B8FA3]">Create your account</p>
        </div>

        <div className="bg-[#1A1A2E]/50 backdrop-blur-sm rounded-2xl p-8 border border-[#555770]/30">
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div>
              <label
                htmlFor="fullName"
                className="block text-sm font-medium text-[#8B8FA3] mb-2"
              >
                Full Name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full px-4 py-3 bg-[#0F1117]/50 border border-[#555770]/50 rounded-lg text-white placeholder-[#555770] focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:border-transparent transition-all"
                placeholder="John Doe"
              />
            </div>

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-[#8B8FA3] mb-2"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 bg-[#0F1117]/50 border border-[#555770]/50 rounded-lg text-white placeholder-[#555770] focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:border-transparent transition-all"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label
                htmlFor="companyName"
                className="block text-sm font-medium text-[#8B8FA3] mb-2"
              >
                Company Name{' '}
                <span className="text-[#555770]">(optional)</span>
              </label>
              <input
                id="companyName"
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="w-full px-4 py-3 bg-[#0F1117]/50 border border-[#555770]/50 rounded-lg text-white placeholder-[#555770] focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:border-transparent transition-all"
                placeholder="Acme Inc."
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-[#8B8FA3] mb-2"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 bg-[#0F1117]/50 border border-[#555770]/50 rounded-lg text-white placeholder-[#555770] focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:border-transparent transition-all"
                placeholder="Min 8 chars, 1 uppercase, 1 number"
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-sm font-medium text-[#8B8FA3] mb-2"
              >
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="w-full px-4 py-3 bg-[#0F1117]/50 border border-[#555770]/50 rounded-lg text-white placeholder-[#555770] focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:border-transparent transition-all"
                placeholder="Confirm your password"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-4 bg-[#2E66FF] hover:bg-[#2255DD] disabled:bg-[#2E66FF]/50 text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-[#2E66FF] focus:ring-offset-2 focus:ring-offset-[#0A0A0B]"
            >
              {isLoading ? (
                <span className="flex items-center justify-center">
                  <svg
                    className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Creating account...
                </span>
              ) : (
                'Create account'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-[#8B8FA3] text-sm">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-[#2E66FF] hover:text-[#5A8AFF] font-medium transition-colors"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
