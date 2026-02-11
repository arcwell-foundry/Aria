import { useState } from "react";
import { X, Save, Loader2 } from "lucide-react";
import type { CustomSkill } from "@/api/skills";
import { useUpdateCustomSkill } from "@/hooks/useSkills";

interface SkillEditSlideOverProps {
  skill: CustomSkill;
  open: boolean;
  onClose: () => void;
}

export function SkillEditSlideOver({
  skill,
  open,
  onClose,
}: SkillEditSlideOverProps) {
  const [prevSkillId, setPrevSkillId] = useState(skill.id);
  const [name, setName] = useState(skill.skill_name);
  const [description, setDescription] = useState(skill.description ?? "");
  const [definitionJson, setDefinitionJson] = useState(
    JSON.stringify(skill.definition, null, 2)
  );
  const [jsonError, setJsonError] = useState<string | null>(null);
  const updateSkill = useUpdateCustomSkill();

  // Reset form state when skill changes (React-recommended pattern)
  if (skill.id !== prevSkillId) {
    setPrevSkillId(skill.id);
    setName(skill.skill_name);
    setDescription(skill.description ?? "");
    setDefinitionJson(JSON.stringify(skill.definition, null, 2));
    setJsonError(null);
  }

  const handleSave = () => {
    let parsedDef: Record<string, unknown> | undefined;
    try {
      parsedDef = JSON.parse(definitionJson);
      setJsonError(null);
    } catch {
      setJsonError("Invalid JSON");
      return;
    }

    updateSkill.mutate(
      {
        skillId: skill.id,
        data: {
          skill_name: name !== skill.skill_name ? name : undefined,
          description: description !== (skill.description ?? "") ? description : undefined,
          definition: parsedDef,
        },
      },
      { onSuccess: onClose }
    );
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-96 bg-slate-900 border-l border-slate-700 z-50 flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">Edit Skill</h3>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Definition (JSON)
            </label>
            <textarea
              value={definitionJson}
              onChange={(e) => {
                setDefinitionJson(e.target.value);
                setJsonError(null);
              }}
              rows={12}
              className={`w-full px-3 py-2 bg-slate-800 border rounded-lg text-white text-sm font-mono focus:outline-none resize-none ${
                jsonError
                  ? "border-critical focus:border-critical"
                  : "border-slate-700 focus:border-primary-500"
              }`}
            />
            {jsonError && (
              <p className="mt-1 text-xs text-critical">{jsonError}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || updateSkill.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-500 rounded-lg transition-colors disabled:opacity-50"
          >
            {updateSkill.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save
          </button>
        </div>
      </div>
    </>
  );
}
