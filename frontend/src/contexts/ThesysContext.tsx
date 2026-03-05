import { createContext, useContext, type ReactNode } from 'react';
import { ThemeProvider as C1ThemeProvider } from '@thesysai/genui-sdk';
import type { Theme } from '@crayonai/react-ui';

const INTER = '"Inter", sans-serif';

const ariaDarkTheme: Theme = {
  // ── Fills ──
  backgroundFills: '#0F1117',
  containerFills: '#161B2E',
  elevatedFills: '#1C2235',
  sunkFills: '#0B0D14',
  sunkBgFills: '#0B0D14',
  overlayFills: 'rgba(0, 0, 0, 0.6)',
  invertedFills: '#E8E6E1',
  dangerFills: '#3B1219',
  successFills: '#0F2918',
  infoFills: '#0F1B38',
  alertFills: '#2E1F0A',

  // ── Strokes ──
  strokeDefault: 'rgba(255, 255, 255, 0.10)',
  strokeEmphasis: 'rgba(255, 255, 255, 0.20)',
  strokeAccent: '#2E66FF',
  strokeAccentEmphasis: '#5A8AFF',
  strokeInfo: '#2E66FF',
  strokeSuccess: '#22C55E',
  strokeAlert: '#F59E0B',
  strokeDanger: '#EF4444',

  // ── Text ──
  primaryText: '#E8E6E1',
  secondaryText: '#9CA3AF',
  disabledText: '#4B5563',
  linkText: '#5A8AFF',
  accentPrimaryText: '#FFFFFF',
  accentSecondaryText: '#C5D4FF',
  successPrimaryText: '#22C55E',
  alertPrimaryText: '#F59E0B',
  dangerPrimaryText: '#EF4444',
  infoPrimaryText: '#5A8AFF',

  // ── Interactive ──
  interactiveDefault: '#1C2235',
  interactiveHover: '#232A42',
  interactivePressed: '#2A3352',
  interactiveDisabled: '#111827',
  interactiveAccent: '#2E66FF',
  interactiveAccentHover: '#4578FF',
  interactiveAccentPressed: '#1A4FE6',
  interactiveAccentDisabled: '#1A2A5C',

  // ── Chat ──
  chatContainerBg: 'transparent',
  chatAssistantResponseBg: 'transparent',
  chatAssistantResponseText: '#E8E6E1',

  // ── Typography (Inter) ──
  fontBody: `400 14px/20px ${INTER}`,
  fontBodyHeavy: `600 14px/20px ${INTER}`,
  fontBodySmall: `400 13px/18px ${INTER}`,
  fontBodySmallHeavy: `600 13px/18px ${INTER}`,
  fontBodyLarge: `400 16px/24px ${INTER}`,
  fontBodyLargeHeavy: `600 16px/24px ${INTER}`,
  fontLabel: `500 13px/16px ${INTER}`,
  fontLabelHeavy: `600 13px/16px ${INTER}`,
  fontLabelSmall: `500 11px/14px ${INTER}`,
  fontLabelSmallHeavy: `600 11px/14px ${INTER}`,
  fontLabelExtraSmall: `500 10px/12px ${INTER}`,
  fontLabelExtraSmallHeavy: `600 10px/12px ${INTER}`,
  fontHeadingLarge: `700 18px/24px ${INTER}`,
  fontHeadingMedium: `600 15px/20px ${INTER}`,
  fontHeadingSmall: `600 13px/18px ${INTER}`,
  fontHeadingExtraSmall: `600 12px/16px ${INTER}`,
  fontNumber: `500 14px/20px ${INTER}`,
  fontNumberHeavy: `700 14px/20px ${INTER}`,
  fontNumberSmall: `500 13px/18px ${INTER}`,
  fontNumberLarge: `500 18px/24px ${INTER}`,
  fontNumberLargeHeavy: `700 18px/24px ${INTER}`,

  // ── Chart palette (dark-mode friendly) ──
  defaultChartPalette: [
    '#2E66FF', '#22C55E', '#F59E0B', '#EF4444',
    '#8B5CF6', '#06B6D4', '#EC4899', '#84CC16',
  ],
};

interface ThesysContextValue {
  enabled: boolean;
}

const ThesysContext = createContext<ThesysContextValue>({ enabled: false });

export function useThesys() {
  return useContext(ThesysContext);
}

interface ThesysProviderProps {
  children: ReactNode;
  enabled?: boolean;
}

export function ThesysProvider({ children, enabled = false }: ThesysProviderProps) {
  if (!enabled) {
    return (
      <ThesysContext.Provider value={{ enabled: false }}>
        {children}
      </ThesysContext.Provider>
    );
  }

  return (
    <ThesysContext.Provider value={{ enabled: true }}>
      <C1ThemeProvider mode="dark" darkTheme={ariaDarkTheme}>
        {children}
      </C1ThemeProvider>
    </ThesysContext.Provider>
  );
}
