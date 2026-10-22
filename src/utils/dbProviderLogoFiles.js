import postgresql from '../assets/db-providers/postgresql.svg';
import mysql from '../assets/db-providers/mysql.svg';
import mariadbWordmark from '../assets/db-providers/mariadb-wordmark.svg';
import microsoftSqlServer from '../assets/db-providers/microsoft-sql-server.svg';
import oracle from '../assets/db-providers/oracle.svg';
import ibmWordmark from '../assets/db-providers/ibm-wordmark.svg';
import snowflake from '../assets/db-providers/snowflake.svg';
import googleBigqueryWordmark from '../assets/db-providers/google-bigquery-wordmark.svg';
import aws from '../assets/db-providers/aws.svg';
import databricks from '../assets/db-providers/databricks.svg';
import clickhouse from '../assets/db-providers/clickhouse.svg';

function resolveSvgUrl(mod) {
  if (!mod) return null;
  if (typeof mod === 'string') return mod;
  const value = mod?.src ?? mod?.default?.src ?? mod?.default ?? mod;
  return typeof value === 'string' ? value : null;
}

/** Bundled SVG URLs keyed by provider id (avoids locale middleware breaking /public paths). */
export const DB_PROVIDER_LOGO_SRC = {
  postgres: resolveSvgUrl(postgresql),
  mysql: resolveSvgUrl(mysql),
  mariadb: resolveSvgUrl(mariadbWordmark),
  mssql: resolveSvgUrl(microsoftSqlServer),
  oracle: resolveSvgUrl(oracle),
  db2: resolveSvgUrl(ibmWordmark),
  snowflake: resolveSvgUrl(snowflake),
  bigquery: resolveSvgUrl(googleBigqueryWordmark),
  redshift: resolveSvgUrl(aws),
  databricks: resolveSvgUrl(databricks),
  clickhouse: resolveSvgUrl(clickhouse),
};

export function dbProviderLogoSrc(providerId) {
  if (!providerId) return null;
  return DB_PROVIDER_LOGO_SRC[providerId] ?? null;
}
