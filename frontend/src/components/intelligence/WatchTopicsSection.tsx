/**
 * WatchTopicsSection - Custom watch topics management for Intelligence page
 *
 * Displays user's watched topics with match counts. Allows adding/removing topics.
 * Data from GET/POST/DELETE /api/v1/intelligence/watch-topics.
 */

import { useState } from 'react';
import { Eye, Plus, X, Search } from 'lucide-react';
import {
  useWatchTopics,
  useAddWatchTopic,
  useDeleteWatchTopic,
} from '@/hooks/useIntelPanelData';
import { formatRelativeTime } from '@/hooks/useIntelPanelData';

type TopicType = 'keyword' | 'company' | 'therapeutic_area';

const TOPIC_TYPE_LABELS: Record<TopicType, string> = {
  keyword: 'Keyword',
  company: 'Company',
  therapeutic_area: 'Therapeutic Area',
};

function AddTopicModal({ onClose }: { onClose: () => void }) {
  const [topicType, setTopicType] = useState<TopicType>('keyword');
  const [topicValue, setTopicValue] = useState('');
  const [description, setDescription] = useState('');
  const addMutation = useAddWatchTopic();

  const handleSubmit = () => {
    if (!topicValue.trim()) return;
    addMutation.mutate(
      {
        topic_type: topicType,
        topic_value: topicValue.trim(),
        description: description.trim() || undefined,
      },
      {
        onSuccess: () => onClose(),
      },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.4)', backdropFilter: 'blur(2px)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full max-w-md rounded-xl border p-6"
        style={{
          backgroundColor: '#FFFFFF',
          borderColor: '#E2E8F0',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold" style={{ color: '#1E293B' }}>
            Add Watch Topic
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
            <X className="w-4 h-4" style={{ color: '#94A3B8' }} />
          </button>
        </div>

        <div className="space-y-4">
          {/* Type select */}
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#5B6E8A' }}>
              Type
            </label>
            <select
              value={topicType}
              onChange={(e) => setTopicType(e.target.value as TopicType)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              style={{
                borderColor: '#E2E8F0',
                color: '#1E293B',
                backgroundColor: '#FFFFFF',
              }}
            >
              {Object.entries(TOPIC_TYPE_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          {/* Value input */}
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#5B6E8A' }}>
              Value
            </label>
            <input
              type="text"
              value={topicValue}
              onChange={(e) => setTopicValue(e.target.value)}
              placeholder="e.g. chromatography resin shortage"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              style={{
                borderColor: '#E2E8F0',
                color: '#1E293B',
              }}
              autoFocus
            />
          </div>

          {/* Description input */}
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#5B6E8A' }}>
              Description <span style={{ color: '#94A3B8' }}>(optional)</span>
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Why this topic matters to you"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              style={{
                borderColor: '#E2E8F0',
                color: '#1E293B',
              }}
            />
          </div>

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!topicValue.trim() || addMutation.isPending}
            className="w-full rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
            style={{
              backgroundColor: 'var(--accent, #2E66FF)',
              color: '#FFFFFF',
            }}
          >
            {addMutation.isPending ? 'Adding...' : 'Add Topic'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function WatchTopicsSection() {
  const { data: topicsData, isLoading } = useWatchTopics();
  const deleteMutation = useDeleteWatchTopic();
  const [showAddModal, setShowAddModal] = useState(false);

  const topics = topicsData?.topics ?? [];

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2
          className="text-base font-medium flex items-center gap-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <Eye className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Watched Topics
          {topics.length > 0 && (
            <span
              className="text-xs font-normal ml-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              ({topics.length})
            </span>
          )}
        </h2>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{
            backgroundColor: '#F8FAFC',
            color: 'var(--accent, #2E66FF)',
            border: '1px solid #E2E8F0',
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          Add Topic
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2 animate-pulse">
          <div className="h-16 rounded-xl" style={{ backgroundColor: '#F1F5F9' }} />
          <div className="h-16 rounded-xl" style={{ backgroundColor: '#F1F5F9' }} />
        </div>
      ) : topics.length === 0 ? (
        <div
          className="rounded-xl border p-6 text-center"
          style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
        >
          <Search className="w-6 h-6 mx-auto mb-2" style={{ color: '#CBD5E1' }} />
          <p className="text-sm" style={{ color: '#5B6E8A' }}>
            No watched topics yet. Add topics to track specific competitors, keywords, or therapeutic areas.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {topics.map((topic) => (
            <div
              key={topic.id}
              className="rounded-xl border p-4 flex items-center justify-between"
              style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium" style={{ color: '#1E293B' }}>
                    &ldquo;{topic.topic_value}&rdquo;
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium tracking-wide"
                    style={{ backgroundColor: '#F1F5F9', color: '#64748B' }}
                  >
                    {TOPIC_TYPE_LABELS[topic.topic_type as TopicType] ?? topic.topic_type}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs" style={{ color: '#94A3B8' }}>
                  <span>{topic.signal_count} match{topic.signal_count !== 1 ? 'es' : ''}</span>
                  {topic.last_matched_at && (
                    <span>Last: {formatRelativeTime(topic.last_matched_at)}</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(topic.id)}
                disabled={deleteMutation.isPending}
                className="p-1.5 rounded-md hover:bg-gray-100 transition-colors flex-shrink-0 ml-3"
                title="Remove topic"
              >
                <X className="w-4 h-4" style={{ color: '#94A3B8' }} />
              </button>
            </div>
          ))}
        </div>
      )}

      {showAddModal && <AddTopicModal onClose={() => setShowAddModal(false)} />}
    </section>
  );
}
