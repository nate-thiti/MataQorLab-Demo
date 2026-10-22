# Disaster Recovery Drill Checklist

- [ ] Confirm production and staging Supabase project refs differ
- [ ] Restore latest backup into an isolated project
- [ ] Restore one Storage prefix and verify object ACL remains owner-scoped
- [ ] Boot API against restored DB and pass `/health/ready`
- [ ] Login with a staging test user and open Files + Chat
- [ ] Confirm DatasetVersion lineage and one dashboard generate
- [ ] Measure actual RPO/RTO and store evidence

Date:
Operator:
Measured RPO:
Measured RTO:
Notes:
