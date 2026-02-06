# US-927: Team & Company Administration Design

**Date:** 2026-02-06
**Story:** US-927 - Team & Company Administration
**Sprint:** 9.3 - SaaS Infrastructure

## Overview

Implements team management and company administration for ARIA. The system allows company admins to manage team members through invitations, role changes, and user activation/deactivation. Following the "open with escalation" policy, any team member can invite others, but companies without a verified admin get flagged for review when they exceed 5 users.

## Architecture

### Backend Components
- `TeamService` (`backend/src/services/team_service.py`) - Core business logic
- Admin routes (`backend/src/api/routes/admin.py`) - API endpoints
- Database migration for `team_invites` table

### Frontend Components
- `AdminTeamPage` (`frontend/src/pages/AdminTeamPage.tsx`) - DARK SURFACE admin interface
- `frontend/src/api/admin.ts` - API client functions
- `frontend/src/hooks/useTeam.ts` - React Query hooks

## Database Schema

### New Table: `team_invites`

```sql
CREATE TABLE IF NOT EXISTS team_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE NOT NULL,
    invited_by UUID REFERENCES auth.users(id) NOT NULL,
    email TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    expires_at TIMESTAMPTZ DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_invite_token ON team_invites(token);
```

### Changes to `user_profiles`
Add `is_active` boolean column for soft deactivation:
```sql
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
```

## Role Hierarchy

| Role | Permissions |
|------|-------------|
| **Admin** | Full access, manage users, billing, all corporate memory |
| **Manager** | Team access, cannot manage billing |
| **User** | Personal access + shared Corporate Memory |

## Key Features

1. **Team Invitations**
   - Any team member can send invites (open with escalation)
   - Unique token per invite (UUID4)
   - 7-day expiry
   - Resend/cancel functionality

2. **Role Management**
   - Change roles (user ↔ manager ↔ admin)
   - Last admin protection (cannot demote last admin)
   - Role-based access control via RLS

3. **User Activation**
   - Soft deactivation (sets `is_active = false`)
   - Reactivation capability
   - Status indicator in team table

4. **Escalation Trigger**
   - Companies with >5 users without verified admin flagged
   - Logged for platform review

5. **Company Details**
   - Edit company name (admins only)
   - View company domain

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/admin/team` | List team members | Admin/Manager |
| POST | `/admin/team/invite` | Create invite | Any user |
| GET | `/admin/team/invites` | List pending invites | Admin |
| POST | `/admin/team/invites/{id}/cancel` | Cancel invite | Admin |
| POST | `/admin/team/invites/{id}/resend` | Resend invite | Admin |
| PATCH | `/admin/team/{user_id}/role` | Change role | Admin |
| POST | `/admin/team/{user_id}/deactivate` | Deactivate user | Admin |
| POST | `/admin/team/{user_id}/reactivate` | Reactivate user | Admin |
| GET | `/admin/company` | Get company details | Admin/Manager |
| PATCH | `/admin/company` | Update company | Admin |

## Frontend: Admin Team Page

**Route:** `/admin/team`
**Theme:** DARK SURFACE (per ARIA Design System)
**Max-width:** 960px

### Components
1. Header with "Invite Member" button
2. Invite modal (email + role dropdown)
3. Team table (name, email, role badge, status dot, last active, actions)
4. Pending invites section (email, role, sent date, resend/cancel actions)
5. Company details section (editable name, read-only domain)

### Design System Compliance
- Instrument Serif for headings
- Satoshi for UI elements
- JetBrains Mono for data/numbers
- Lucide React icons (20x20, stroke 1.5)
- 4px spacing grid
- DARK SURFACE colors (#0F1117, #161B2E, #2A2A2E)
- WCAG AA accessibility

## Security Considerations

1. **RLS Enforcement**
   - Roles enforced at database level
   - Admins see all team data
   - Managers see team directory (names, roles only)
   - Digital Twin privacy maintained via RLS

2. **Audit Logging**
   - All team management events logged
   - Escalation triggers logged for review

3. **Input Validation**
   - Email validation on invites
   - Role enum validation
   - Last admin protection

## Testing Requirements

- Invite creates unique token
- Cannot demote last admin (400 error)
- Non-admin gets 403 on admin routes
- Deactivation flag persists
- Invite expiry enforced

## Implementation Order

1. Database migration
2. TeamService implementation
3. Admin routes
4. Frontend API client and hooks
5. AdminTeamPage component
6. Route registration
7. Testing and quality gates

## Dependencies

- Phase 1 (Auth foundation)
- US-926 (Account & Identity Management)
- ARIA Design System v1.0
