/** Database provider catalog for connection UI (industry-standard targets). */

export const DB_PROVIDER_CATEGORIES = [
  { id: 'relational', labelEn: 'Relational', labelTh: 'ฐานข้อมูลเชิงสัมพันธ์' },
  { id: 'warehouse', labelEn: 'Cloud & analytics', labelTh: 'Cloud / Analytics' },
];

export const DATABASE_PROVIDERS = [
  {
    id: 'postgres',
    label: 'PostgreSQL',
    category: 'relational',
    defaultPort: '5432',
    hostPlaceholder: 'db.example.com',
    dbPlaceholder: 'production_db',
  },
  {
    id: 'mysql',
    label: 'MySQL',
    category: 'relational',
    defaultPort: '3306',
    hostPlaceholder: 'db.example.com',
    dbPlaceholder: 'my_database',
  },
  {
    id: 'mariadb',
    label: 'MariaDB',
    category: 'relational',
    defaultPort: '3306',
    hostPlaceholder: 'db.example.com',
    dbPlaceholder: 'my_database',
  },
  {
    id: 'mssql',
    label: 'SQL Server',
    category: 'relational',
    defaultPort: '1433',
    hostPlaceholder: 'sql.example.com',
    dbPlaceholder: 'master',
  },
  {
    id: 'oracle',
    label: 'Oracle',
    category: 'relational',
    defaultPort: '1521',
    hostPlaceholder: 'oracle.example.com',
    dbPlaceholder: 'ORCL',
    dbLabelEn: 'Service name / SID',
    dbLabelTh: 'Service name / SID',
  },
  {
    id: 'db2',
    label: 'IBM Db2',
    category: 'relational',
    defaultPort: '50000',
    hostPlaceholder: 'db2.example.com',
    dbPlaceholder: 'SAMPLE',
  },
  {
    id: 'snowflake',
    label: 'Snowflake',
    category: 'warehouse',
    defaultPort: '443',
    hostPlaceholder: 'xy12345.us-east-1.snowflakecomputing.com',
    dbPlaceholder: 'MY_DATABASE',
    hostLabelEn: 'Account host',
    hostLabelTh: 'Account host',
  },
  {
    id: 'bigquery',
    label: 'Google BigQuery',
    category: 'warehouse',
    defaultPort: '443',
    hostPlaceholder: 'my-gcp-project',
    dbPlaceholder: 'my_dataset',
    hostLabelEn: 'GCP project ID',
    hostLabelTh: 'GCP project ID',
    dbLabelEn: 'Dataset',
    dbLabelTh: 'Dataset',
  },
  {
    id: 'redshift',
    label: 'Amazon Redshift',
    category: 'warehouse',
    defaultPort: '5439',
    hostPlaceholder: 'cluster.id.region.redshift.amazonaws.com',
    dbPlaceholder: 'dev',
  },
  {
    id: 'databricks',
    label: 'Databricks',
    category: 'warehouse',
    defaultPort: '443',
    hostPlaceholder: 'adb-xxx.azuredatabricks.net',
    dbPlaceholder: 'default',
    hostLabelEn: 'Workspace host',
    hostLabelTh: 'Workspace host',
  },
  {
    id: 'clickhouse',
    label: 'ClickHouse',
    category: 'warehouse',
    defaultPort: '8123',
    hostPlaceholder: 'clickhouse.example.com',
    dbPlaceholder: 'default',
  },
];

export function getDatabaseProvider(id) {
  return DATABASE_PROVIDERS.find((p) => p.id === id) || DATABASE_PROVIDERS[0];
}

export function getProviderLabel(id) {
  return getDatabaseProvider(id).label;
}

export function defaultPortForProvider(id) {
  return getDatabaseProvider(id).defaultPort;
}

export function providersByCategory(categoryId) {
  return DATABASE_PROVIDERS.filter((p) => p.category === categoryId);
}
