export const hasOrganizationCustomerAccess = (plan, governance) => {
  const planName = String(plan?.name || '').trim().toLowerCase();
  const hasBusinessPlan = planName === 'business' || planName === 'enterprise';
  const hasOrganizationMembership = Array.isArray(governance?.organizations)
    && governance.organizations.some((membership) => (
      membership?.organization_id || membership?.organizations?.id
    ));
  return hasBusinessPlan || hasOrganizationMembership;
};
