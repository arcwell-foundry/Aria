/**
 * useIsMounted — Track component mount status for async safety
 *
 * Prevents React error #300 (setState on unmounted component) by
 * providing a callback to check if the component is still mounted.
 *
 * @example
 * const isMounted = useIsMounted();
 * useEffect(() => {
 *   wsManager.on('event', () => {
 *     if (!isMounted()) return;
 *     setState(newValue);
 *   });
 * }, []);
 */

import { useCallback, useEffect, useRef } from 'react';

export function useIsMounted(): () => boolean {
  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  return useCallback(() => isMountedRef.current, []);
}
