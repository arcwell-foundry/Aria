import { Edit3, StickyNote } from "lucide-react";
import { useState } from "react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface BriefNotesSectionProps {
  initialNotes?: string;
  onSave?: (notes: string) => void;
}

export function BriefNotesSection({ initialNotes = "", onSave }: BriefNotesSectionProps) {
  const [notes, setNotes] = useState(initialNotes);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (onSave) {
      setIsSaving(true);
      try {
        await onSave(notes);
      } finally {
        setIsSaving(false);
      }
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setNotes(initialNotes);
    setIsEditing(false);
  };

  return (
    <CollapsibleSection
      title="Your Notes"
      icon={<StickyNote className="w-5 h-5" />}
      badgeColor="slate"
      defaultExpanded={!!initialNotes}
    >
      <div className="space-y-3">
        {isEditing ? (
          <>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add your notes for this meeting..."
              className="w-full h-32 px-4 py-3 bg-slate-700/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none"
              autoFocus
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 text-sm bg-primary-600 hover:bg-primary-500 disabled:opacity-60 text-white font-medium rounded-lg transition-colors"
              >
                {isSaving ? "Saving..." : "Save notes"}
              </button>
            </div>
          </>
        ) : (
          <div
            onClick={() => setIsEditing(true)}
            className="group cursor-pointer p-4 bg-slate-700/30 border border-slate-600/30 hover:border-primary-500/30 rounded-lg transition-colors"
          >
            {notes ? (
              <p className="text-slate-300 whitespace-pre-wrap">{notes}</p>
            ) : (
              <div className="flex items-center gap-2 text-slate-400 group-hover:text-primary-400 transition-colors">
                <Edit3 className="w-4 h-4" />
                <span>Click to add notes...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
