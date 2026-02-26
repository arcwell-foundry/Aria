/**
 * Route Validation Utilities
 *
 * Provides validation functions for navigation routes and resource IDs
 * to prevent malformed URL navigation and injection attacks.
 *
 * @example
 * if (isValidRoute(cmd.route)) {
 *   navigate(cmd.route);
 * }
 *
 * if (isValidLeadId(lead.id)) {
 *   navigate(`/pipeline/leads/${lead.id}`);
 * }
 */

/**
 * Valid route patterns for ARIA application.
 * Only routes matching these patterns will be allowed.
 */
const VALID_ROUTES: RegExp[] = [
  /^\/$/,                                    // Home
  /^\/dialogue/,                             // Dialogue mode
  /^\/briefing/,                             // Briefing pages
  /^\/pipeline$/,                            // Pipeline list
  /^\/pipeline\/leads\/[^/]+$/,              // Lead detail (any ID)
  /^\/actions/,                              // Actions pages
  /^\/settings/,                             // Settings pages
  /^\/communications/,                       // Communications pages
  /^\/activity/,                             // Activity log
  /^\/intelligence/,                         // Intelligence panel
  /^\/onboarding/,                           // Onboarding flow
];

/**
 * UUID v4 pattern for validating resource IDs.
 */
const UUID_PATTERN: RegExp = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Validates that a route string is a well-formed internal route.
 *
 * Rejects:
 * - Empty or undefined routes
 * - Routes containing protocol strings (http://, https://)
 * - Malformed routes like ":1" or "pipeline:1"
 * - Routes not matching known ARIA patterns
 *
 * @param route - The route string to validate
 * @returns true if the route is valid, false otherwise
 */
export function isValidRoute(route: string | undefined): boolean {
  if (!route || typeof route !== 'string') return false;

  // Reject routes with protocol (external URLs)
  if (route.includes('://')) return false;

  // Reject malformed routes like ":1" or "pipeline:1"
  // These typically indicate template interpolation errors
  if (route.includes(':') && !route.startsWith('/')) return false;

  // Reject routes that start with colon (e.g., ":1", ":3000/pipeline")
  if (route.startsWith(':')) return false;

  // Must start with / for internal routes
  if (!route.startsWith('/')) return false;

  // Check against valid route patterns
  return VALID_ROUTES.some((pattern) => pattern.test(route));
}

/**
 * Validates that a lead ID is well-formed.
 *
 * Accepts:
 * - UUID v4 format (standard database IDs)
 * - Numeric IDs (legacy or alternative formats)
 *
 * @param id - The lead ID to validate
 * @returns true if the ID is valid, false otherwise
 */
export function isValidLeadId(id: string | undefined): boolean {
  if (!id || typeof id !== 'string') return false;

  // Accept UUID v4 format
  if (UUID_PATTERN.test(id)) return true;

  // Accept numeric IDs (positive integers only)
  if (/^\d+$/.test(id)) return true;

  return false;
}

/**
 * Validates a generic resource ID (used for drafts, actions, etc.)
 *
 * Currently accepts the same formats as lead IDs but separated
 * for potential future customization.
 *
 * @param id - The resource ID to validate
 * @returns true if the ID is valid, false otherwise
 */
export function isValidResourceId(id: string | undefined): boolean {
  return isValidLeadId(id);
}
