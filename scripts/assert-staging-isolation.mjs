const required = [
  'STAGING_APP_URL',
  'STAGING_API_URL',
  'STAGING_SUPABASE_URL',
];

for (const key of required) {
  if (!process.env[key]) throw new Error(`Missing required staging variable: ${key}`);
}

const normalizeHost = (value) => new URL(value).host.toLowerCase();
const stagingHosts = new Set(required.map((key) => normalizeHost(process.env[key])));
const productionUrls = [
  process.env.PRODUCTION_APP_URL,
  process.env.PRODUCTION_API_URL,
  process.env.PRODUCTION_SUPABASE_URL,
].filter(Boolean);
if (!productionUrls.length && !process.env.PRODUCTION_SUPABASE_PROJECT_REF) {
  throw new Error(
    'Configure a production URL or PRODUCTION_SUPABASE_PROJECT_REF for isolation.',
  );
}

for (const productionUrl of productionUrls) {
  const productionHost = normalizeHost(productionUrl);
  if (stagingHosts.has(productionHost)) {
    throw new Error(`Staging isolation failed: ${productionHost} is configured as production.`);
  }
}

const stagingSupabaseHost = normalizeHost(process.env.STAGING_SUPABASE_URL);
const productionRef = String(process.env.PRODUCTION_SUPABASE_PROJECT_REF || '')
  .trim()
  .toLowerCase();
if (productionRef && stagingSupabaseHost.startsWith(`${productionRef}.`)) {
  throw new Error('Staging isolation failed: Supabase project matches production.');
}

if (!/^https:\/\//.test(process.env.STAGING_APP_URL)) {
  throw new Error('STAGING_APP_URL must use HTTPS.');
}

console.log('Staging isolation guard passed.');
