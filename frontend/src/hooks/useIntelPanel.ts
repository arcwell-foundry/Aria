import { useContext } from 'react';
import { IntelPanelCtx, type IntelPanelContextValue } from '@/contexts/IntelPanelContext';

export function useIntelPanel(): IntelPanelContextValue {
  const ctx = useContext(IntelPanelCtx);
  if (!ctx) {
    throw new Error('useIntelPanel must be used within IntelPanelProvider');
  }
  return ctx;
}
