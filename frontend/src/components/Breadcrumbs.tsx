/**
 * Breadcrumbs component - Shows navigation path.
 *
 * Following ARIA Design System v1.0:
 * - Satoshi Caption size
 * - Muted, clickable segments
 * - ChevronRight separator (14px)
 */

import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  href: string;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav className="flex items-center gap-1 text-caption text-secondary">
      {items.map((item, index) => (
        <div key={item.href} className="flex items-center gap-1">
          {index > 0 && (
            <ChevronRight size={14} strokeWidth={1.5} className="shrink-0" />
          )}
          <Link
            to={item.href}
            className="hover:text-interactive transition-colors duration-150 truncate max-w-[200px]"
          >
            {item.label}
          </Link>
        </div>
      ))}
    </nav>
  );
}
