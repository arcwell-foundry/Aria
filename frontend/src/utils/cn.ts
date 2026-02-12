/**
 * cn - Utility function for conditionally joining class names
 *
 * A lightweight alternative to clsx/cn for class name composition.
 * Handles strings, numbers, objects, and arrays.
 *
 * @example
 * cn('base-class', condition && 'conditional-class', { 'active': isActive })
 * // Returns: 'base-class conditional-class active' (if condition and isActive are true)
 */

type ClassValue = string | number | boolean | undefined | null | ClassValue[];

export function cn(...inputs: ClassValue[]): string {
  const classes: string[] = [];

  for (const input of inputs) {
    if (!input) continue;

    if (typeof input === 'string' || typeof input === 'number') {
      classes.push(String(input));
    } else if (Array.isArray(input)) {
      const inner = cn(...input);
      if (inner) classes.push(inner);
    } else if (typeof input === 'object') {
      for (const [key, value] of Object.entries(input)) {
        if (value) classes.push(key);
      }
    }
  }

  return classes.join(' ');
}
