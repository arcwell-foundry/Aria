import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import {
  SkeletonLoader,
  CardSkeleton,
  ListSkeleton,
  TableSkeleton,
  TextSkeleton,
  LeadsSkeleton,
  GoalsSkeleton,
  BriefingSkeleton,
  LeadsTableSkeleton,
  ContactsListSkeleton,
} from '../SkeletonLoader';

describe('SkeletonLoader', () => {
  describe('Base SkeletonLoader Component', () => {
    it('renders text variant by default', () => {
      render(<SkeletonLoader />);
      const skeletons = document.querySelectorAll('.bg-\\[\\#2A2F42\\]');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('renders specified count of skeleton items', () => {
      render(<SkeletonLoader variant="card" count={3} />);
      const cards = document.querySelectorAll('.bg-\\[\\#161B2E\\]');
      expect(cards.length).toBe(3);
    });

    it('applies custom className', () => {
      render(<SkeletonLoader variant="text" className="mt-4" />);
      const container = document.querySelector('.space-y-2.mt-4');
      expect(container).toBeInTheDocument();
    });

    it('renders card variant', () => {
      const { container } = render(<SkeletonLoader variant="card" />);
      expect(container.querySelector('.rounded-xl')).toBeInTheDocument();
      expect(container.querySelector('.border-\\[\\#2A2F42\\]')).toBeInTheDocument();
    });

    it('renders list variant', () => {
      const { container } = render(<SkeletonLoader variant="list" />);
      expect(container.querySelector('.rounded-full')).toBeInTheDocument();
    });

    it('renders table variant with default columns', () => {
      const { container } = render(
        <table>
          <tbody>
            <SkeletonLoader variant="table" />
          </tbody>
        </table>
      );
      const cells = container.querySelectorAll('td');
      expect(cells.length).toBe(8); // checkbox + 6 data columns + actions
    });
  });

  describe('CardSkeleton', () => {
    it('renders card structure with all elements', () => {
      const { container } = render(<CardSkeleton />);
      const card = container.querySelector('.bg-\\[\\#161B2E\\]');
      expect(card).toBeInTheDocument();
      expect(card).toHaveClass('border', 'border-border', 'rounded-xl');
    });

    it('has header section with avatar placeholder', () => {
      const { container } = render(<CardSkeleton />);
      const avatar = container.querySelector('.w-12.h-12');
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveClass('rounded-xl');
    });

    it('has badge/status placeholder', () => {
      const { container } = render(<CardSkeleton />);
      const badge = container.querySelector('.rounded-full');
      expect(badge).toBeInTheDocument();
    });

    it('has meta info grid', () => {
      const { container } = render(<CardSkeleton />);
      const grid = container.querySelector('.grid');
      expect(grid).toBeInTheDocument();
      expect(grid).toHaveClass('grid-cols-2');
    });

    it('has tags section with border', () => {
      const { container } = render(<CardSkeleton />);
      const tagsSection = container.querySelector('.border-t');
      expect(tagsSection).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(<CardSkeleton className="mt-2" />);
      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('mt-2');
    });
  });

  describe('ListSkeleton', () => {
    it('renders list item structure', () => {
      const { container } = render(<ListSkeleton />);
      const item = container.querySelector('.bg-\\[\\#161B2E\\]');
      expect(item).toBeInTheDocument();
      expect(item).toHaveClass('border', 'border-border', 'rounded-xl');
    });

    it('has avatar placeholder', () => {
      const { container } = render(<ListSkeleton />);
      const avatar = container.querySelector('.w-10.h-10');
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveClass('rounded-full');
    });

    it('has content lines', () => {
      const { container } = render(<ListSkeleton />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      expect(lines.length).toBeGreaterThanOrEqual(2);
    });

    it('has action button placeholder', () => {
      const { container } = render(<ListSkeleton />);
      const action = container.querySelector('.w-8.h-8');
      expect(action).toBeInTheDocument();
      expect(action).toHaveClass('rounded-lg');
    });
  });

  describe('TableSkeleton', () => {
    it('renders table row with correct structure', () => {
      const { container } = render(
        <table>
          <tbody>
            <TableSkeleton />
          </tbody>
        </table>
      );
      const row = container.querySelector('tr');
      expect(row).toBeInTheDocument();
      expect(row).toHaveClass('border-b');
    });

    it('renders checkbox column', () => {
      const { container } = render(
        <table>
          <tbody>
            <TableSkeleton />
          </tbody>
        </table>
      );
      const checkbox = container.querySelector('.w-5.h-5');
      expect(checkbox).toBeInTheDocument();
    });

    it('respects custom column count', () => {
      const { container } = render(
        <table>
          <tbody>
            <TableSkeleton columns={5} />
          </tbody>
        </table>
      );
      // checkbox + (columns - 2) data columns + actions = columns total
      const cells = container.querySelectorAll('td');
      expect(cells.length).toBe(5);
    });

    it('has actions column with button placeholders', () => {
      const { container } = render(
        <table>
          <tbody>
            <TableSkeleton />
          </tbody>
        </table>
      );
      const actions = container.querySelectorAll('.w-8.h-8');
      expect(actions.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe('TextSkeleton', () => {
    it('renders default 3 lines', () => {
      const { container } = render(<TextSkeleton />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      expect(lines.length).toBe(3);
    });

    it('renders custom number of lines', () => {
      const { container } = render(<TextSkeleton lines={5} />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      expect(lines.length).toBe(5);
    });

    it('last line is shorter (creates visual taper)', () => {
      const { container } = render(<TextSkeleton lines={3} />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      const lastLine = lines[lines.length - 1] as HTMLElement;
      expect(lastLine).toHaveClass('w-2/3');
    });

    it('all lines except last are full width', () => {
      const { container } = render(<TextSkeleton lines={4} />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      for (let i = 0; i < lines.length - 1; i++) {
        expect(lines[i]).toHaveClass('w-full');
      }
    });

    it('applies custom className', () => {
      const { container } = render(<TextSkeleton className="p-4" />);
      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper).toHaveClass('p-4');
    });
  });

  describe('LeadsSkeleton', () => {
    it('renders card view mode by default', () => {
      const { container } = render(<LeadsSkeleton />);
      const grid = container.querySelector('.grid');
      expect(grid).toBeInTheDocument();
      expect(grid).toHaveClass('md:grid-cols-2', 'xl:grid-cols-3');
    });

    it('renders default 6 cards in card mode', () => {
      const { container } = render(<LeadsSkeleton viewMode="card" />);
      const cards = container.querySelectorAll('.bg-\\[\\#161B2E\\].rounded-xl');
      expect(cards.length).toBe(6);
    });

    it('respects custom count in card mode', () => {
      const { container } = render(<LeadsSkeleton viewMode="card" count={3} />);
      const cards = container.querySelectorAll('.bg-\\[\\#161B2E\\].rounded-xl');
      expect(cards.length).toBe(3);
    });

    it('renders table mode with structure', () => {
      const { container } = render(<LeadsSkeleton viewMode="table" />);
      const table = container.querySelector('table');
      expect(table).toBeInTheDocument();

      const thead = container.querySelector('thead');
      expect(thead).toBeInTheDocument();

      const headers = thead?.querySelectorAll('th');
      expect(headers?.length).toBe(8); // checkbox + 7 columns
    });

    it('table has correct column headers', () => {
      render(<LeadsSkeleton viewMode="table" />);
      expect(screen.getByText('Company')).toBeInTheDocument();
      expect(screen.getByText('Health')).toBeInTheDocument();
      expect(screen.getByText('Stage')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Value')).toBeInTheDocument();
      expect(screen.getByText('Last Activity')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
    });

    it('renders specified count in table mode', () => {
      const { container } = render(<LeadsSkeleton viewMode="table" count={3} />);
      const rows = container.querySelectorAll('tbody tr');
      expect(rows.length).toBe(3);
    });
  });

  describe('GoalsSkeleton', () => {
    it('renders goals grid layout', () => {
      const { container } = render(<GoalsSkeleton />);
      const grid = container.querySelector('.grid');
      expect(grid).toBeInTheDocument();
      expect(grid).toHaveClass('md:grid-cols-2', 'lg:grid-cols-3');
    });

    it('renders default 6 goal cards', () => {
      const { container } = render(<GoalsSkeleton />);
      const cards = container.querySelectorAll('.bg-\\[\\#161B2E\\]');
      expect(cards.length).toBe(6);
    });

    it('respects custom count', () => {
      const { container } = render(<GoalsSkeleton count={4} />);
      const cards = container.querySelectorAll('.bg-\\[\\#161B2E\\]');
      expect(cards.length).toBe(4);
    });

    it('has progress ring placeholder', () => {
      const { container } = render(<GoalsSkeleton />);
      const progressRing = container.querySelector('.w-14.h-14.rounded-full');
      expect(progressRing).toBeInTheDocument();
    });

    it('has badge placeholders', () => {
      const { container } = render(<GoalsSkeleton />);
      const badges = container.querySelectorAll('.rounded-full');
      expect(badges.length).toBeGreaterThan(0);
    });

    it('has agent count placeholder', () => {
      const { container } = render(<GoalsSkeleton />);
      // First card should have agent count line
      const firstCard = container.querySelector('.bg-\\[\\#161B2E\\]');
      const agentLine = firstCard?.querySelector('.w-32');
      expect(agentLine).toBeInTheDocument();
    });
  });

  describe('BriefingSkeleton', () => {
    it('renders greeting section', () => {
      const { container } = render(<BriefingSkeleton />);
      const greeting = container.querySelector('.space-y-3');
      expect(greeting).toBeInTheDocument();

      const lines = greeting?.querySelectorAll('.bg-\\[\\#2A2F42\\]');
      expect(lines?.length).toBe(2);
    });

    it('renders executive summary card', () => {
      const { container } = render(<BriefingSkeleton />);
      const summary = container.querySelectorAll('.rounded-xl')[0];
      expect(summary).toBeInTheDocument();
      expect(summary).toHaveClass('p-6');
    });

    it('renders 4 section cards', () => {
      const { container } = render(<BriefingSkeleton />);
      // First is summary, rest are sections
      const sections = container.querySelectorAll('.rounded-xl');
      expect(sections.length).toBe(5); // 1 summary + 4 sections
    });

    it('section cards have headers with icons', () => {
      const { container } = render(<BriefingSkeleton />);
      const sections = container.querySelectorAll('.rounded-xl');
      const firstSection = sections[1]; // Skip summary

      const icon = firstSection.querySelector('.w-5.h-5');
      expect(icon).toBeInTheDocument();
    });

    it('section cards have content area', () => {
      const { container } = render(<BriefingSkeleton />);
      const sections = container.querySelectorAll('.rounded-xl');
      const firstSection = sections[1];

      const content = firstSection.querySelector('.space-y-3');
      expect(content).toBeInTheDocument();

      const items = content?.querySelectorAll('.rounded-lg');
      expect(items?.length).toBe(2);
    });
  });

  describe('LeadsTableSkeleton', () => {
    it('is an alias for LeadsSkeleton in table mode', () => {
      const { container: tableContainer } = render(<LeadsTableSkeleton count={3} />);
      const { container: leadsContainer } = render(<LeadsSkeleton viewMode="table" count={3} />);

      const tableRows = tableContainer.querySelectorAll('tbody tr');
      const leadsRows = leadsContainer.querySelectorAll('tbody tr');

      expect(tableRows.length).toBe(leadsRows.length);
      expect(tableRows.length).toBe(3);
    });

    it('renders default 5 rows', () => {
      const { container } = render(<LeadsTableSkeleton />);
      const rows = container.querySelectorAll('tbody tr');
      expect(rows.length).toBe(5);
    });
  });

  describe('ContactsListSkeleton', () => {
    it('renders list items in vertical layout', () => {
      const { container } = render(<ContactsListSkeleton />);
      const items = container.querySelectorAll('.bg-\\[\\#161B2E\\].rounded-xl');
      expect(items.length).toBe(8);
    });

    it('respects custom count', () => {
      const { container } = render(<ContactsListSkeleton count={5} />);
      const items = container.querySelectorAll('.bg-\\[\\#161B2E\\].rounded-xl');
      expect(items.length).toBe(5);
    });

    it('items have list structure (avatar + content + action)', () => {
      const { container } = render(<ContactsListSkeleton count={1} />);
      const avatar = container.querySelector('.rounded-full');
      const action = container.querySelector('.rounded-lg');

      expect(avatar).toBeInTheDocument();
      expect(action).toBeInTheDocument();
    });
  });

  describe('TextSkeleton Export', () => {
    it('exports TextSkeleton as named export', () => {
      expect(TextSkeleton).toBeDefined();
      expect(typeof TextSkeleton).toBe('function');
    });

    it('renders correctly with default props', () => {
      const { container } = render(<TextSkeleton />);
      const lines = container.querySelectorAll('.space-y-2 > div');
      expect(lines.length).toBe(3);
    });
  });

  describe('ARIA Design System Compliance', () => {
    it('uses correct skeleton color bg-border', () => {
      render(<CardSkeleton />);
      const skeleton = document.querySelector('.bg-\\[\\#2A2F42\\]');
      expect(skeleton).toBeInTheDocument();
    });

    it('uses correct surface background bg-elevated', () => {
      render(<CardSkeleton />);
      const surface = document.querySelector('.bg-\\[\\#161B2E\\]');
      expect(surface).toBeInTheDocument();
    });

    it('uses correct border color border-border', () => {
      render(<CardSkeleton />);
      const border = document.querySelector('.border-\\[\\#2A2F42\\]');
      expect(border).toBeInTheDocument();
    });

    it('all skeletons have animate-pulse class', () => {
      const { container } = render(
        <>
          <CardSkeleton />
          <ListSkeleton />
          <TextSkeleton />
        </>
      );

      const animatedElements = container.querySelectorAll('.animate-pulse');
      expect(animatedElements.length).toBeGreaterThan(0);
    });

    it('rounded corners follow design system', () => {
      const { container } = render(<CardSkeleton />);
      const card = container.querySelector('.rounded-xl');
      expect(card).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('skeletons do not have semantic meaning', () => {
      render(<LeadsSkeleton viewMode="card" count={1} />);
      // Should not have heading, button, or other semantic roles
      const buttons = screen.queryAllByRole('button');
      expect(buttons.length).toBe(0);
    });

    it('does not interfere with screen readers', () => {
      render(<BriefingSkeleton />);
      // Skeletons should not announce content
      const liveRegions = screen.queryAllByRole('status');
      expect(liveRegions.length).toBe(0);
    });
  });

  describe('Integration Patterns', () => {
    it('can be used as direct replacement for content', () => {
      const TestComponent = ({ loading }: { loading: boolean }) => {
        if (loading) {
          return <LeadsSkeleton viewMode="card" count={2} />;
        }
        return <div>Real content</div>;
      };

      const { container } = render(<TestComponent loading={true} />);
      expect(screen.queryByText('Real content')).not.toBeInTheDocument();
      expect(container.querySelector('.grid')).toBeInTheDocument();
    });

    it('supports conditional rendering patterns', () => {
      const isLoading = true;

      render(
        <div>
          {isLoading ? (
            <SkeletonLoader variant="card" count={3} />
          ) : (
            <div>Loaded content</div>
          )}
        </div>
      );

      expect(screen.queryByText('Loaded content')).not.toBeInTheDocument();
    });
  });
});
