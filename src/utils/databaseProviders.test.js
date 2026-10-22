import { describe, expect, it } from 'vitest';
import {
  DATABASE_PROVIDERS,
  defaultPortForProvider,
  getProviderLabel,
  providersByCategory,
} from './databaseProviders.js';

describe('databaseProviders', () => {
  it('includes all requested warehouse and relational providers', () => {
    const ids = DATABASE_PROVIDERS.map((p) => p.id);
    expect(ids).toEqual(
      expect.arrayContaining([
        'postgres',
        'mysql',
        'mariadb',
        'mssql',
        'oracle',
        'db2',
        'snowflake',
        'bigquery',
        'redshift',
        'databricks',
        'clickhouse',
      ])
    );
    expect(ids).toHaveLength(11);
  });

  it('returns default ports per provider', () => {
    expect(defaultPortForProvider('postgres')).toBe('5432');
    expect(defaultPortForProvider('snowflake')).toBe('443');
    expect(defaultPortForProvider('clickhouse')).toBe('8123');
  });

  it('groups providers by category', () => {
    expect(providersByCategory('relational').length).toBe(6);
    expect(providersByCategory('warehouse').length).toBe(5);
  });

  it('resolves display labels', () => {
    expect(getProviderLabel('mariadb')).toBe('MariaDB');
    expect(getProviderLabel('unknown')).toBe('PostgreSQL');
  });
});
