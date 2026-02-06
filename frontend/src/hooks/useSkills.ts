import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAvailableSkills,
  listInstalledSkills,
  installSkill,
  uninstallSkill,
  getSkillAudit,
  type AvailableSkillsFilters,
} from "@/api/skills";

// Query keys
export const skillKeys = {
  all: ["skills"] as const,
  available: () => [...skillKeys.all, "available"] as const,
  availableFiltered: (filters?: AvailableSkillsFilters) =>
    [...skillKeys.available(), { filters }] as const,
  installed: () => [...skillKeys.all, "installed"] as const,
  audit: () => [...skillKeys.all, "audit"] as const,
  auditFiltered: (skillId?: string) =>
    [...skillKeys.audit(), { skillId }] as const,
};

// List available skills
export function useAvailableSkills(filters?: AvailableSkillsFilters) {
  return useQuery({
    queryKey: skillKeys.availableFiltered(filters),
    queryFn: () => listAvailableSkills(filters),
  });
}

// List installed skills
export function useInstalledSkills() {
  return useQuery({
    queryKey: skillKeys.installed(),
    queryFn: () => listInstalledSkills(),
  });
}

// Install skill mutation
export function useInstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => installSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Uninstall skill mutation
export function useUninstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => uninstallSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Skill audit log
export function useSkillAudit(skillId?: string) {
  return useQuery({
    queryKey: skillKeys.auditFiltered(skillId),
    queryFn: () => getSkillAudit(skillId),
  });
}
