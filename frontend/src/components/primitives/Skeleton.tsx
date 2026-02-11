/**
 * Skeleton - Loading placeholder following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Base: bg-border (animated pulse)
 * - Container: bg-elevated, border-border
 *
 * @example
 * <Skeleton variant="text" lines={3} />
 * <Skeleton variant="card" count={3} />
 * <Skeleton variant="circle" size="lg" />
 */

export interface SkeletonProps {
  /** Number of skeleton items to render */
  count?: number;
  /** Skeleton variant */
  variant?: "text" | "circle" | "rect" | "card" | "list";
  /** Width (for rect/circle variants) */
  width?: string | number;
  /** Height (for rect variant) */
  height?: string | number;
  /** Size preset (for circle variant) */
  size?: "sm" | "md" | "lg";
  /** Number of text lines (for text variant) */
  lines?: number;
  /** Additional CSS classes */
  className?: string;
}

const sizePresets = {
  sm: "w-8 h-8",
  md: "w-12 h-12",
  lg: "w-16 h-16",
};

/** Base skeleton element */
function SkeletonBase({
  className = "",
  width,
  height,
}: {
  className?: string;
  width?: string | number;
  height?: string | number;
}) {
  const style = {
    width: width ? (typeof width === "number" ? `${width}px` : width) : undefined,
    height: height ? (typeof height === "number" ? `${height}px` : height) : undefined,
  };

  return (
    <div
      className={`bg-border animate-pulse rounded ${className}`}
      style={style}
    />
  );
}

/** Text skeleton with multiple lines */
function TextSkeleton({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBase
          key={i}
          className={`h-4 ${i === lines - 1 ? "w-2/3" : "w-full"}`}
        />
      ))}
    </div>
  );
}

/** Circle skeleton (avatar placeholder) */
function CircleSkeleton({
  size = "md",
  className = "",
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return (
    <SkeletonBase
      className={`rounded-full ${sizePresets[size]} ${className}`}
    />
  );
}

/** Rectangular skeleton */
function RectSkeleton({
  width = "100%",
  height = 100,
  className = "",
}: {
  width?: string | number;
  height?: string | number;
  className?: string;
}) {
  return (
    <SkeletonBase
      width={width}
      height={height}
      className={className}
    />
  );
}

/** Card skeleton placeholder */
function CardSkeleton({
  className = "",
}: {
  className?: string;
}) {
  return (
    <div
      className={`bg-elevated border border-border rounded-xl p-5 overflow-hidden ${className}`}
    >
      {/* Header section */}
      <div className="flex items-start gap-4 mb-4">
        <SkeletonBase className="w-12 h-12 rounded-xl flex-shrink-0" />
        <div className="flex-1 min-w-0 space-y-2">
          <SkeletonBase className="h-5 w-3/4" />
          <SkeletonBase className="h-4 w-1/2" />
        </div>
      </div>
      {/* Badge area */}
      <div className="mb-4">
        <SkeletonBase className="h-6 w-20 rounded-full" />
      </div>
      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-3">
        <SkeletonBase className="h-4" />
        <SkeletonBase className="h-4" />
      </div>
    </div>
  );
}

/** List item skeleton placeholder */
function ListSkeleton({
  className = "",
}: {
  className?: string;
}) {
  return (
    <div
      className={`bg-elevated border border-border rounded-xl p-4 ${className}`}
    >
      <div className="flex items-center gap-3">
        <SkeletonBase className="w-10 h-10 rounded-full flex-shrink-0" />
        <div className="flex-1 min-w-0 space-y-2">
          <SkeletonBase className="h-4 w-48" />
          <SkeletonBase className="h-3 w-32" />
        </div>
        <SkeletonBase className="w-8 h-8 rounded-lg flex-shrink-0" />
      </div>
    </div>
  );
}

export function Skeleton({
  count = 1,
  variant = "rect",
  width,
  height,
  size = "md",
  lines = 3,
  className = "",
}: SkeletonProps) {
  const renderSkeleton = () => {
    switch (variant) {
      case "text":
        return <TextSkeleton lines={lines} className={className} />;
      case "circle":
        return <CircleSkeleton size={size} className={className} />;
      case "card":
        return <CardSkeleton className={className} />;
      case "list":
        return <ListSkeleton className={className} />;
      case "rect":
      default:
        return <RectSkeleton width={width} height={height} className={className} />;
    }
  };

  if (count === 1) {
    return renderSkeleton();
  }

  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i}>{renderSkeleton()}</div>
      ))}
    </>
  );
}

// Named exports for specific variants
export { SkeletonBase, TextSkeleton, CircleSkeleton, RectSkeleton, CardSkeleton, ListSkeleton };
