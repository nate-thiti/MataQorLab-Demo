import { describe, expect, it } from 'vitest';

import { hasOrganizationCustomerAccess } from './customerCenterAccess.js';

describe('hasOrganizationCustomerAccess', () => {
  it.each(['Free', 'Plus', 'Pro'])('keeps %s accounts in individual mode', (name) => {
    expect(hasOrganizationCustomerAccess({ name }, { organizations: [] })).toBe(false);
  });

  it.each(['Business', 'Enterprise'])('enables organization controls for %s', (name) => {
    expect(hasOrganizationCustomerAccess({ name }, { organizations: [] })).toBe(true);
  });

  it('enables organization controls for an invited organization member', () => {
    expect(hasOrganizationCustomerAccess(
      { name: 'Free' },
      { organizations: [{ organization_id: 'org-1', role: 'member' }] },
    )).toBe(true);
  });
});
