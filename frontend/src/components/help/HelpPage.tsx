import { useState } from "react";
import { Search, MessageSquare, Mail } from "lucide-react";

interface FAQArticle {
  id: string;
  question: string;
  answer: string;
}

interface FAQCategory {
  id: string;
  title: string;
  icon: React.ReactNode;
  articles: FAQArticle[];
}

const FAQ_CATEGORIES: FAQCategory[] = [
  {
    id: "getting-started",
    title: "Getting Started",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "gs-1",
        question: "What is ARIA and how can it help me?",
        answer: "ARIA (Autonomous Reasoning & Intelligence Agent) is your AI-powered Department Director for Life Sciences commercial teams. She helps you reduce administrative work from 72% to under 20%, allowing you to focus on what matters most - selling and building relationships.",
      },
      {
        id: "gs-2",
        question: "How do I complete the initial onboarding?",
        answer: "Onboarding consists of several steps where ARIA learns about your company, goals, and communication style. Simply follow the guided steps, provide information when requested, and ARIA will progressively build her understanding of your business context.",
      },
      {
        id: "gs-3",
        question: "What integrations does ARIA support?",
        answer: "ARIA integrates with major CRM systems (Salesforce, HubSpot), email platforms (Gmail, Outlook), calendar systems, and various data sources. Visit Settings > Integrations to see all available connections.",
      },
      {
        id: "gs-4",
        question: "How long until ARIA is fully productive?",
        answer: "ARIA becomes more capable as she learns. Basic features are available immediately after onboarding. Full intelligence typically develops over 2-4 weeks as she processes your communications, meetings, and interactions.",
      },
    ],
  },
  {
    id: "features",
    title: "Features & Capabilities",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "feat-1",
        question: "How does the meeting briefing feature work?",
        answer: "ARIA automatically generates comprehensive meeting briefs by combining her knowledge of attendees, company context, previous interactions, and relevant signals. Briefs are available 30 minutes before scheduled meetings.",
      },
      {
        id: "feat-2",
        question: "Can ARIA help with email drafting?",
        answer: "Yes. ARIA can draft emails based on your communication style and the context of the conversation. Simply provide the key points you want to convey, and she'll create a personalized draft that you can edit and send.",
      },
      {
        id: "feat-3",
        question: "What are Battle Cards and how do I use them?",
        answer: "Battle Cards are strategic documents that help you competitive situations. ARIA generates real-time battle cards with competitive intelligence, objection handling, and value messaging tailored to each sales opportunity.",
      },
      {
        id: "feat-4",
        question: "How does goal tracking work?",
        answer: "You can set quarterly goals in the Goals section. ARIA tracks progress, identifies risks, and proactively suggests actions to keep you on target. She also learns from your goals to better prioritize her assistance.",
      },
      {
        id: "feat-5",
        question: "What is the Skills system?",
        answer: "Skills are specialized capabilities that ARIA can deploy. They include advanced analysis, content generation, research tasks, and workflow automation. Skills are configured based on your needs and preferences.",
      },
    ],
  },
  {
    id: "memory",
    title: "Memory & Intelligence",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "mem-1",
        question: "What does ARIA remember about my contacts?",
        answer: "ARIA builds a comprehensive understanding of your contacts including communication history, relationships, preferences, and context. She maintains both individual profiles and relationship maps between contacts.",
      },
      {
        id: "mem-2",
        question: "How does ARIA use my communication history?",
        answer: "With your permission, ARIA analyzes email communications (securely and privately) to understand your communication style, relationships, and business context. This helps her provide more personalized assistance.",
      },
      {
        id: "mem-3",
        question: "Can I correct information ARIA has learned?",
        answer: "Absolutely. Whenever ARIA shares something she learned, you'll see confidence indicators and can provide corrections. These corrections help improve her accuracy and are treated as high-confidence information.",
      },
      {
        id: "mem-4",
        question: "Is my data secure?",
        answer: "Yes. All data is encrypted at rest and in transit. We use enterprise-grade security practices, and your data is never shared with other users or companies. ARIA's Digital Twin (personal style) is never shared, even within your company.",
      },
    ],
  },
  {
    id: "settings",
    title: "Settings & Configuration",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "set-1",
        question: "How do I configure my communication preferences?",
        answer: "Visit Settings > Preferences to adjust how ARIA communicates with you. You can set notification frequency, message tone, detail level, and formality to match your working style.",
      },
      {
        id: "set-2",
        question: "How do I manage integrations?",
        answer: "Go to Settings > Integrations to view, add, or remove connected services. Each integration can be configured with specific sync preferences and data sharing controls.",
      },
      {
        id: "set-3",
        question: "Can I control what data ARIA accesses?",
        answer: "Yes. In Settings > Privacy, you can control data access permissions, retention policies, and what types of information ARIA can use. You maintain full control over your data.",
      },
      {
        id: "set-4",
        question: "How do I update my account information?",
        answer: "Navigate to Settings > Account to update your profile, contact information, and password. Company administrators can manage team settings from the Admin section.",
      },
    ],
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "tr-1",
        question: "ARIA isn't responding to my requests. What should I do?",
        answer: "First, check your internet connection. If the issue persists, try refreshing the page. If problems continue, contact support with details about what you were trying to do and any error messages you received.",
      },
      {
        id: "tr-2",
        question: "My integrations aren't syncing properly.",
        answer: "Go to Settings > Integrations and check the connection status. Try disconnecting and reconnecting the integration. If the issue persists, ensure you have the necessary permissions and that the integration service is operational.",
      },
      {
        id: "tr-3",
        question: "ARIA's suggestions don't seem relevant lately.",
        answer: "This can happen when your context or priorities have changed. Use the feedback mechanism on suggestions to help ARIA recalibrate. You can also update your goals and preferences to realign her understanding.",
      },
      {
        id: "tr-4",
        question: "I'm seeing slower performance than usual.",
        answer: "Performance can be affected by large data processing tasks, network conditions, or system load. If slowness persists, check the System Health dashboard and consider clearing your browser cache.",
      },
    ],
  },
  {
    id: "billing",
    title: "Billing & Plans",
    icon: <MessageSquare className="w-5 h-5" />,
    articles: [
      {
        id: "bill-1",
        question: "What pricing plans are available?",
        answer: "ARIA is offered as a premium SaaS at $200K/year per organization. This includes full access to all features, unlimited users within your company, and dedicated support.",
      },
      {
        id: "bill-2",
        question: "How do I update payment information?",
        answer: "Company administrators can update payment methods in Settings > Admin > Billing. We accept all major credit cards and can arrange for invoice payments for enterprise customers.",
      },
      {
        id: "bill-3",
        question: "Is there a free trial available?",
        answer: "Contact our sales team to discuss pilot programs and trial options. We work with qualified organizations to demonstrate value before commitment.",
      },
      {
        id: "bill-4",
        question: "How do I add or remove team members?",
        answer: "Team administrators can manage users in Settings > Admin > Team. Adding users requires available seats in your subscription. New users complete onboarding to personalize their ARIA experience.",
      },
    ],
  },
];

export function HelpPageContent() {
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(["getting-started"]));
  const [expandedArticles, setExpandedArticles] = useState<Set<string>>(new Set());

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) {
        next.delete(categoryId);
      } else {
        next.add(categoryId);
      }
      return next;
    });
  };

  const toggleArticle = (articleId: string) => {
    setExpandedArticles((prev) => {
      const next = new Set(prev);
      if (next.has(articleId)) {
        next.delete(articleId);
      } else {
        next.add(articleId);
      }
      return next;
    });
  };

  // Filter categories and articles based on search query
  const filteredCategories = FAQ_CATEGORIES.map((category) => ({
    ...category,
    articles: category.articles.filter(
      (article) =>
        article.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
        article.answer.toLowerCase().includes(searchQuery.toLowerCase())
    ),
  })).filter((category) => category.articles.length > 0 || searchQuery === "");

  return (
    <div className="bg-primary min-h-screen">
      <div className="max-w-4xl mx-auto px-6 py-8 lg:px-8 lg:py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Help Center</h1>
          <p className="mt-2 text-slate-600">
            Find answers to common questions and learn how to make the most of ARIA
          </p>
        </div>

        {/* Search Bar */}
        <div className="mb-8">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search for help..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent bg-white text-slate-900 placeholder-slate-400"
            />
          </div>
        </div>

        {/* FAQ Categories */}
        <div className="space-y-4">
          {filteredCategories.map((category) => {
            const isExpanded = expandedCategories.has(category.id) || searchQuery !== "";
            const showCategory = searchQuery === "" || category.articles.length > 0;

            if (!showCategory) return null;

            return (
              <div
                key={category.id}
                className="bg-white rounded-lg border border-slate-200 overflow-hidden"
              >
                {/* Category Header */}
                <button
                  onClick={() => toggleCategory(category.id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
                  disabled={searchQuery !== ""}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary-100 text-primary-600">
                      {category.icon}
                    </div>
                    <h2 className="text-lg font-semibold text-slate-900">{category.title}</h2>
                  </div>
                  {searchQuery === "" && (
                    <svg
                      className={`w-5 h-5 text-slate-400 transition-transform ${
                        isExpanded ? "rotate-180" : ""
                      }`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  )}
                </button>

                {/* Articles */}
                {isExpanded && (
                  <div className="border-t border-slate-200">
                    <div className="divide-y divide-slate-100">
                      {category.articles.map((article) => {
                        const isArticleExpanded = expandedArticles.has(article.id);
                        return (
                          <div key={article.id} className="px-6">
                            <button
                              onClick={() => toggleArticle(article.id)}
                              className="w-full py-4 flex items-start justify-between text-left hover:bg-slate-50 -mx-6 px-6 transition-colors"
                            >
                              <span className="font-medium text-slate-800 pr-4">
                                {article.question}
                              </span>
                              <svg
                                className={`flex-shrink-0 w-5 h-5 text-slate-400 transition-transform mt-0.5 ${
                                  isArticleExpanded ? "rotate-180" : ""
                                }`}
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M19 9l-7 7-7-7"
                                />
                              </svg>
                            </button>
                            {isArticleExpanded && (
                              <div className="pb-4 -mx-6 px-6">
                                <p className="text-slate-600 leading-relaxed">{article.answer}</p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Contact Support */}
        <div className="mt-12 p-6 bg-white rounded-lg border border-slate-200">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 flex items-center justify-center w-12 h-12 rounded-lg bg-primary-100 text-primary-600">
              <Mail className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-900 mb-2">Still need help?</h3>
              <p className="text-slate-600 mb-4">
                Our support team is here to assist you. We typically respond within 24 hours.
              </p>
              <a
                href="mailto:support@aria.ai"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium"
              >
                <Mail className="w-4 h-4" />
                Contact Support
              </a>
            </div>
          </div>
        </div>

        {/* Feedback Widget */}
        <div className="mt-6 text-center">
          <p className="text-sm text-slate-500">
            Found this helpful?{" "}
            <a href="/feedback" className="text-primary-600 hover:text-primary-700 font-medium">
              Share your feedback
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
