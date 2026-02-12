import { useState, useEffect } from "react";
import { X, Sparkles, Save, Search, Loader2, CheckCircle } from "lucide-react";
import { useICP, useSaveICP, useDiscoverLeads } from "@/hooks/useLeadGeneration";
import type { ICPDefinition } from "@/hooks/useLeadGeneration";

function TagInput({
  label,
  tags,
  onAdd,
  onRemove,
  placeholder,
}: {
  label: string;
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (index: number) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && input.trim()) {
      e.preventDefault();
      onAdd(input.trim());
      setInput("");
    }
  };
  return (
    <div>
      <label className="block text-sm font-medium text-slate-300 mb-1.5">
        {label}
      </label>
      <div className="flex flex-wrap gap-2 mb-2">
        {tags.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-slate-700 text-slate-200 px-2.5 py-1 rounded-md text-sm"
          >
            {tag}
            <button
              onClick={() => onRemove(i)}
              className="text-slate-400 hover:text-slate-200"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-primary-500"
      />
    </div>
  );
}

export function ICPBuilder() {
  const { data: icpResponse, isLoading: isLoadingICP } = useICP();
  const saveICPMutation = useSaveICP();
  const discoverMutation = useDiscoverLeads();

  const [industry, setIndustry] = useState<string[]>([]);
  const [modalities, setModalities] = useState<string[]>([]);
  const [therapeuticAreas, setTherapeuticAreas] = useState<string[]>([]);
  const [geographies, setGeographies] = useState<string[]>([]);
  const [signals, setSignals] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [companySizeMin, setCompanySizeMin] = useState<number>(0);
  const [companySizeMax, setCompanySizeMax] = useState<number>(10000);
  const [icpSaved, setIcpSaved] = useState(false);

  // Load existing ICP data
  const icpData = icpResponse?.icp_data;
  useEffect(() => {
    if (icpData) {
      const applyIcp = () => {
        setIndustry(icpData.industry);
        setModalities(icpData.modalities);
        setTherapeuticAreas(icpData.therapeutic_areas);
        setGeographies(icpData.geographies);
        setSignals(icpData.signals);
        setExclusions(icpData.exclusions);
        setCompanySizeMin(icpData.company_size.min);
        setCompanySizeMax(icpData.company_size.max);
        setIcpSaved(true);
      };
      applyIcp();
    }
  }, [icpData]);

  const buildICPDefinition = (): ICPDefinition => ({
    industry,
    modalities,
    therapeutic_areas: therapeuticAreas,
    geographies,
    signals,
    exclusions,
    company_size: { min: companySizeMin, max: companySizeMax },
  });

  const handleSave = () => {
    saveICPMutation.mutate(buildICPDefinition(), {
      onSuccess: () => setIcpSaved(true),
    });
  };

  const handleDiscover = () => {
    discoverMutation.mutate(undefined);
  };

  const addTag = (
    setter: React.Dispatch<React.SetStateAction<string[]>>
  ) => {
    return (tag: string) => setter((prev) => [...prev, tag]);
  };

  const removeTag = (
    setter: React.Dispatch<React.SetStateAction<string[]>>
  ) => {
    return (index: number) =>
      setter((prev) => prev.filter((_, i) => i !== index));
  };

  if (isLoadingICP) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
        <span className="ml-2 text-slate-400">Loading ICP...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ARIA Suggestions */}
      <div className="bg-primary-900/20 border border-primary-700/30 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-primary-400 mt-0.5 shrink-0" />
          <div>
            <h3 className="text-sm font-medium text-primary-300 mb-1">
              ARIA Suggestions
            </h3>
            <p className="text-sm text-slate-300">
              Based on your company profile, consider targeting:{" "}
              <span className="text-primary-300">Biotech</span> companies,{" "}
              <span className="text-primary-300">Biologics</span> modality,{" "}
              <span className="text-primary-300">North America</span> geography
            </p>
          </div>
        </div>
      </div>

      {/* Form Card */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 space-y-6">
        <h2 className="text-lg font-semibold text-white">
          Ideal Customer Profile
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <TagInput
            label="Industry"
            tags={industry}
            onAdd={addTag(setIndustry)}
            onRemove={removeTag(setIndustry)}
            placeholder="e.g. Biotechnology, Pharma..."
          />
          <TagInput
            label="Modalities"
            tags={modalities}
            onAdd={addTag(setModalities)}
            onRemove={removeTag(setModalities)}
            placeholder="e.g. Biologics, Small Molecule..."
          />
          <TagInput
            label="Therapeutic Areas"
            tags={therapeuticAreas}
            onAdd={addTag(setTherapeuticAreas)}
            onRemove={removeTag(setTherapeuticAreas)}
            placeholder="e.g. Oncology, Immunology..."
          />
          <TagInput
            label="Geographies"
            tags={geographies}
            onAdd={addTag(setGeographies)}
            onRemove={removeTag(setGeographies)}
            placeholder="e.g. North America, Europe..."
          />
          <TagInput
            label="Signals"
            tags={signals}
            onAdd={addTag(setSignals)}
            onRemove={removeTag(setSignals)}
            placeholder="e.g. Series C, Hiring ramp..."
          />
          <TagInput
            label="Exclusions"
            tags={exclusions}
            onAdd={addTag(setExclusions)}
            onRemove={removeTag(setExclusions)}
            placeholder="e.g. Generic manufacturers..."
          />
        </div>

        {/* Company Size */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">
            Company Size (headcount)
          </label>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={companySizeMin}
              onChange={(e) => setCompanySizeMin(Number(e.target.value))}
              min={0}
              placeholder="Min"
              className="w-32 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-primary-500"
            />
            <span className="text-slate-500">to</span>
            <input
              type="number"
              value={companySizeMax}
              onChange={(e) => setCompanySizeMax(Number(e.target.value))}
              min={0}
              placeholder="Max"
              className="w-32 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-primary-500"
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saveICPMutation.isPending}
            className="flex items-center gap-2 bg-primary-600 hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          >
            {saveICPMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : saveICPMutation.isSuccess ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saveICPMutation.isPending
              ? "Saving..."
              : saveICPMutation.isSuccess
                ? "Saved"
                : "Save ICP"}
          </button>

          <button
            onClick={handleDiscover}
            disabled={!icpSaved || discoverMutation.isPending}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          >
            {discoverMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : discoverMutation.isSuccess ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {discoverMutation.isPending
              ? "Discovering..."
              : discoverMutation.isSuccess
                ? "Leads Discovered"
                : "Discover Leads"}
          </button>
        </div>
      </div>
    </div>
  );
}
