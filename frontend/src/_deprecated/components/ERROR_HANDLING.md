# Error Handling Components

## Overview
This directory contains reusable error handling components that provide consistent user experience when things go wrong. All components follow ARIA's design system principles.

## Components

### ErrorBoundary

React error boundary that catches JavaScript errors in component trees and displays a fallback UI.

**Usage:**
```tsx
import { ErrorBoundary } from '@/components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary
      fallback={<ErrorFallback message="Something went wrong" />}
      onError={(error) => logError(error)}
    >
      <YourComponent />
    </ErrorBoundary>
  );
}
```

**Props:**
- `fallback`: React node to display on error
- `onError`: Optional callback for error logging
- `resetKeys`: Array of values that trigger reset when changed

**Features:**
- Catches runtime errors in component tree
- Prevents white screen of death
- Provides recovery mechanisms
- Logs errors to monitoring service

### EmptyState

Displays a consistent empty state with optional actions.

**Usage:**
```tsx
import { EmptyState } from '@/components/EmptyState';

<EmptyState
  title="No data found"
  description="Upload your first document to get started"
  icon={<UploadIcon />}
  action={{
    label: "Upload Document",
    onClick: handleUpload
  }}
/>
```

**Props:**
- `title`: Headline text
- `description`: Explanatory text
- `icon`: Optional icon element
- `action`: Optional action button config
- `variant`: 'default' | 'compact'

**Design System Compliance:**
- Uses `text-muted-foreground` for descriptions
- Spacing follows 4px/8px/16px grid
- Icons are 24px with 8px padding
- Actions use primary button styles

### SkeletonLoader

Provides loading placeholders that match content layout.

**Usage:**
```tsx
import { SkeletonLoader } from '@/components/SkeletonLoader';

<SkeletonLoader variant="card" count={3} />
<SkeletonLoader variant="table" rows={10} columns={5} />
<SkeletonLoader variant="text" lines={3} />
```

**Variants:**
- `card`: Card-sized skeletons with header and content
- `table`: Table row skeletons with configurable columns
- `text`: Text line skeletons with realistic width variation
- `circle`: Circular avatar/image placeholder

**Animation:**
- Subtle shimmer effect (opacity 0.5 → 1.0)
- 1.5s duration, infinite loop
- Matches ARIA's motion design principles

### OfflineBanner

Displays when network connectivity is lost.

**Usage:**
```tsx
import { OfflineBanner } from '@/components/OfflineBanner';

function Layout() {
  return (
    <>
      <OfflineBanner />
      {/* App content */}
    </>
  );
}
```

**Features:**
- Automatically detects online/offline status
- Shows dismissible banner when offline
- Auto-hides when connection restored
- Persists dismissal state across sessions

**Styling:**
- Fixed position at bottom of viewport
- Warning color scheme (amber/yellow)
- 48px height with smooth slide animation
- Dismiss button on the right

### ErrorToaster

Toast notifications for errors and warnings.

**Usage:**
```tsx
import { ErrorToaster } from '@/components/ErrorToaster';

// Show error toast
ErrorToaster.show({
  title: "Upload failed",
  message: "Please check your connection and try again",
  type: "error",
  duration: 5000
});

// Show warning
ErrorToaster.show({
  title: "Session expiring soon",
  message: "Save your work to avoid losing changes",
  type: "warning"
});
```

**Types:**
- `error`: Red styling, auto-dismiss after 5s
- `warning`: Yellow styling, auto-dismiss after 5s
- `info`: Blue styling, auto-dismiss after 3s

**Features:**
- Stackable multiple toasts
- Manual dismiss option
- Action buttons (e.g., "Retry", "Learn More")
- ARIA live regions for accessibility

### RetryButton

Intelligent retry button with exponential backoff.

**Usage:**
```tsx
import { RetryButton } from '@/components/RetryButton';

<RetryButton
  onRetry={fetchData}
  maxRetries={3}
  backoffMs={1000}
/>
```

**Features:**
- Shows countdown before retry available
- Implements exponential backoff
- Disables after max retries
- Displays remaining attempts

## Design System Compliance

All error handling components follow these principles:

### Typography
- Headings: `text-lg font-semibold`
- Body: `text-sm text-muted-foreground`
- Consistent hierarchy across all components

### Spacing
- Base unit: 4px
- Component padding: 16px (4 units)
- Gap between elements: 8px or 16px
- Consistent with tailwind.config.js

### Colors
- Errors: `destructive` (red-600)
- Warnings: `warning` (amber-500)
- Info: `primary` (blue-600)
- Neutral: `muted` (gray-500)

### Motion
- Fade transitions: 150-200ms
- Slide animations: 200-300ms
- Skeleton shimmer: 1.5s infinite
- All transitions use `ease-out` timing

### Accessibility
- All errors announced via ARIA live regions
- Keyboard navigation support
- Screen reader-friendly descriptions
- Focus management on error states
- Color contrast WCAG AA compliant

## Integration with API Errors

```tsx
import { useApiError } from '@/hooks/useApiError';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ErrorToaster } from '@/components/ErrorToaster';

function DataComponent() {
  const handleError = useApiError();

  const fetchData = async () => {
    try {
      await api.getData();
    } catch (error) {
      handleError(error, {
        toast: true,
        fallback: "Failed to load data"
      });
    }
  };

  return (
    <ErrorBoundary>
      <button onClick={fetchData}>Load Data</button>
    </ErrorBoundary>
  );
}
```

## Testing

```tsx
import { render, screen } from '@testing-library/react';
import { EmptyState } from '@/components/EmptyState';

describe('EmptyState', () => {
  it('displays title and description', () => {
    render(
      <EmptyState
        title="No data"
        description="Upload to get started"
      />
    );

    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText(/upload/i)).toBeInTheDocument();
  });

  it('calls action callback', () => {
    const onAction = jest.fn();
    render(
      <EmptyState
        title="No data"
        action={{ label: "Upload", onClick: onAction }}
      />
    );

    screen.getByText('Upload').click();
    expect(onAction).toHaveBeenCalled();
  });
});
```

## Best Practices

1. **Always provide context**: Empty states should explain why there's no data and what to do
2. **Offer recovery paths**: Error states should include next steps or retry options
3. **Match content layout**: Skeletons should approximate final content structure
4. **Log errors systematically**: All errors should be logged with context
5. **Graceful degradation**: Features should fail without breaking the entire app
6. **Clear communication**: Use plain language, avoid technical jargon
7. **Consistent placement**: Error messages appear in predictable locations
