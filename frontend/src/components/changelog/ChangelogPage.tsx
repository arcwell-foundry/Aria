import { ArrowRight } from "lucide-react";

interface ChangelogEntry {
  version: string;
  date: string;
  title: string;
  description: string;
  features: string[];
}

const CHANGELOG_ENTRIES: ChangelogEntry[] = [
  {
    version: "v1.3.0",
    date: "2025-02-01",
    title: "Advanced Meeting Intelligence",
    description: "Enhanced meeting preparation with real-time battle cards and competitive intelligence.",
    features: [
      "Real-time Battle Cards with competitive positioning",
      "Advanced meeting briefs with stakeholder analysis",
      "Automatic objection handling suggestions",
      "Post-meeting action item extraction",
    ],
  },
  {
    version: "v1.2.0",
    date: "2025-01-15",
    title: "Skills System Launch",
    description: "Introducing specialized AI skills for complex workflows and research tasks.",
    features: [
      "Deep Research skill for market analysis",
      "Content Generation skill for proposals and collateral",
      "Workflow Automation for repetitive tasks",
      "Custom skill configuration based on user preferences",
    ],
  },
  {
    version: "v1.1.0",
    date: "2025-01-01",
    title: "CRM Integration Enhancement",
    description: "Deeper CRM integration with bidirectional sync and intelligent lead scoring.",
    features: [
      "Two-way Salesforce and HubSpot sync",
      "Intelligent lead scoring based on engagement",
      "Automatic activity logging from communications",
      "Custom field mapping and data transformation",
    ],
  },
  {
    version: "v1.0.0",
    date: "2024-12-15",
    title: "ARIA Launch",
    description: "Initial release of ARIA - Your AI-powered Department Director for Life Sciences.",
    features: [
      "Core AI agent framework (Hunter, Analyst, Strategist, Scribe, Operator, Scout)",
      "Six-type memory system for comprehensive intelligence",
      "Email integration and analysis",
      "Calendar integration for meeting preparation",
      "Goal tracking and progress monitoring",
    ],
  },
];

function isNewEntry(date: string): boolean {
  const entryDate = new Date(date);
  const now = new Date();
  const diffTime = Math.abs(now.getTime() - entryDate.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays <= 7;
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function ChangelogPageContent() {
  return (
    <div className="bg-primary min-h-screen">
      <div className="max-w-4xl mx-auto px-6 py-8 lg:px-8 lg:py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Changelog</h1>
          <p className="mt-2 text-slate-600">
            Stay up to date with the latest features and improvements to ARIA
          </p>
        </div>

        {/* Changelog Entries */}
        <div className="space-y-6">
          {CHANGELOG_ENTRIES.map((entry) => (
            <div
              key={entry.version}
              className="bg-white rounded-lg border border-slate-200 p-6 hover:shadow-md transition-shadow"
            >
              {/* Version Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm px-3 py-1 rounded bg-subtle text-slate-700 font-medium">
                    {entry.version}
                  </span>
                  {isNewEntry(entry.date) && (
                    <span className="px-2 py-1 rounded-full bg-green-100 text-green-700 text-xs font-medium">
                      New
                    </span>
                  )}
                </div>
                <time className="font-mono text-sm text-slate-500" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  {formatDate(entry.date)}
                </time>
              </div>

              {/* Title */}
              <h2 className="text-xl font-medium text-slate-900 mb-2" style={{ fontFamily: "'Satoshi', sans-serif", fontWeight: 500 }}>
                {entry.title}
              </h2>

              {/* Description */}
              <p className="text-slate-600 mb-4">
                {entry.description}
              </p>

              {/* Features List */}
              <ul className="space-y-2">
                {entry.features.map((feature, index) => (
                  <li key={index} className="flex items-start gap-2 text-slate-700">
                    <ArrowRight className="w-4 h-4 text-primary-600 flex-shrink-0 mt-0.5" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-12 text-center">
          <p className="text-slate-600">
            Looking for help with a specific feature?{" "}
            <a href="/help" className="text-primary-600 hover:text-primary-700 font-medium">
              Visit our Help Center
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
