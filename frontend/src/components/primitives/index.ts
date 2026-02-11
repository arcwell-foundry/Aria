/**
 * Primitives - Atomic UI components following ARIA Design System v1.0
 *
 * These components are framework-agnostic building blocks that:
 * - Use CSS variables for theming (dark + light modes)
 * - Support consistent styling across the app
 * - Provide TypeScript prop interfaces
 *
 * @example
 * import { Button, Input, Card, Badge } from '@/components/primitives';
 */

export { Button, type ButtonProps } from './Button';
export { Input, type InputProps } from './Input';
export { Card, type CardProps, type CardHeaderProps, type CardBodyProps, type CardFooterProps } from './Card';
export { Badge, type BadgeProps } from './Badge';
export { ProgressBar, type ProgressBarProps } from './ProgressBar';
export { Avatar, type AvatarProps } from './Avatar';
export { Tooltip, type TooltipProps } from './Tooltip';
export {
  Skeleton,
  SkeletonBase,
  TextSkeleton,
  CircleSkeleton,
  RectSkeleton,
  CardSkeleton,
  ListSkeleton,
  type SkeletonProps
} from './Skeleton';
