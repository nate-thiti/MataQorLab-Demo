import Papa from 'papaparse';
import readXlsxFile from 'read-excel-file/browser';
import { authFetch } from '../../utils/authFetch.js';
import { getPublicApiUrl } from '../../utils/env.js';

const MAX_SAMPLE_BYTES = 512 * 1024;
const MAX_EXCEL_SAMPLE_BYTES = 25 * 1024 * 1024;

function decodeCsvBytes(arrayBuffer) {
  let text = new TextDecoder('utf-8').decode(arrayBuffer);
  if (text.includes('\uFFFD')) {
    try {
      text = new TextDecoder('windows-874').decode(arrayBuffer);
    } catch {
      /* keep utf-8 */
    }
  }
  if (text.length > 0 && text.charCodeAt(0) === 0xfeff) {
    text = text.slice(1);
  }
  return text;
}

function scoreHeaderRow(row, nextRow) {
  const values = (row || []).filter((v) => v !== null && v !== undefined && String(v).trim());
  if (!values.length) return -1;
  const labels = values.map((v) => String(v).trim());
  const uniqueRatio = new Set(labels).size / labels.length;
  const textRatio = labels.filter((v) => /[\p{L}_]/u.test(v)).length / labels.length;
  const unnamedPenalty = labels.filter((v) => v.toLowerCase().startsWith('unnamed')).length;
  let score = labels.length * 2 + uniqueRatio * 3 + textRatio * 2 - unnamedPenalty * 4;
  const nextValues = (nextRow || []).filter((v) => v !== null && v !== undefined && String(v).trim());
  if (nextValues.length >= Math.max(1, Math.floor(labels.length / 2))) score += 2;
  return score;
}

function detectHeaderRow(rows) {
  let bestIdx = 0;
  let bestScore = -1;
  (rows || []).slice(0, 25).forEach((row, idx) => {
    const score = scoreHeaderRow(row, rows[idx + 1]);
    if (score > bestScore) {
      bestScore = score;
      bestIdx = idx;
    }
  });
  return bestIdx;
}

function scoreSheetMatrix(matrix) {
  const rows = (matrix || []).filter((row) =>
    (row || []).some((v) => v !== null && v !== undefined && String(v).trim())
  );
  if (!rows.length) return -1;
  const headerRow = detectHeaderRow(matrix);
  const nonEmptyCells = rows.reduce(
    (count, row) =>
      count + row.filter((v) => v !== null && v !== undefined && String(v).trim()).length,
    0
  );
  return scoreHeaderRow(matrix[headerRow], matrix[headerRow + 1]) + Math.min(rows.length, 10) * 2 + Math.min(nonEmptyCells, 80) * 0.1;
}

function selectWorkbookSheet(workbook) {
  let bestSheet = workbook[0];
  let bestScore = -1;
  for (const sheet of workbook) {
    const score = scoreSheetMatrix(sheet.data);
    if (score > bestScore) {
      bestScore = score;
      bestSheet = sheet;
    }
  }
  return bestSheet;
}

function rowsFromMatrix(matrix, headerRow) {
  const header = (matrix?.[headerRow] || []).map((v, idx) => {
    const label = v !== null && v !== undefined && String(v).trim() ? String(v).trim() : `col_${idx}`;
    return label;
  });
  return (matrix || []).slice(headerRow + 1).map((row) => {
    const rec = {};
    header.forEach((col, idx) => {
      rec[col] = row?.[idx] ?? null;
    });
    return rec;
  });
}

/** Normalize JSON payloads to an array of row objects for column mapping. */
export function normalizeTabularRows(data) {
  if (!data) return [];
  if (Array.isArray(data)) {
    return data.filter((row) => row && typeof row === 'object' && !Array.isArray(row));
  }
  if (typeof data === 'object') {
    for (const value of Object.values(data)) {
      if (
        Array.isArray(value) &&
        value.length > 0 &&
        typeof value[0] === 'object' &&
        !Array.isArray(value[0])
      ) {
        return value;
      }
    }
    return [data];
  }
  return [];
}

export function discoverJsonRecordPaths(data, maxDepth = 6) {
  const paths = [];
  const walk = (node, path, depth) => {
    if (paths.length >= 30 || depth > maxDepth || !node) return;
    if (Array.isArray(node)) {
      if (node.length && node.slice(0, 20).every((item) => item && typeof item === 'object' && !Array.isArray(item))) {
        paths.push(path ? `${path}[]` : '[]');
      }
      node.slice(0, 3).forEach((item) => {
        if (item && typeof item === 'object') walk(item, path ? `${path}[]` : '[]', depth + 1);
      });
      return;
    }
    if (typeof node === 'object') {
      Object.entries(node).forEach(([key, item]) => {
        if (item && typeof item === 'object') walk(item, path ? `${path}.${key}` : key, depth + 1);
      });
    }
  };
  walk(data, '', 0);
  return [...new Set(paths)];
}

export function rowsAtJsonPath(data, path) {
  if (!path) return normalizeTabularRows(data);
  let values = [data];
  for (const part of path.split('.')) {
    const isArray = part.endsWith('[]');
    const key = isArray ? part.slice(0, -2) : part;
    const next = [];
    values.forEach((value) => {
      const child = part === '[]' ? value : (value && typeof value === 'object' && !Array.isArray(value) ? value[key] : undefined);
      if (isArray && Array.isArray(child)) next.push(...child);
      else if (!isArray && child !== undefined) next.push(child);
    });
    values = next;
  }
  return values.filter((row) => row && typeof row === 'object' && !Array.isArray(row));
}

function sliceSample(rows, maxRows = 10) {
  const filtered = (rows || []).filter(
    (row) => row && typeof row === 'object' && Object.keys(row).length > 0
  );
  return filtered.slice(0, maxRows);
}

/**
 * Load a small tabular sample from Supabase Storage for column mapping / preview.
 * Supports csv, json, xlsx, xls, parquet (parquet via backend).
 */
export async function parseFileSample(supabase, userId, fileName, { maxRows = 10, jsonPath = null, includeJsonPaths = false } = {}) {
  const storageName = typeof fileName === 'string' ? fileName.trim() : '';
  if (!storageName || !userId) {
    throw new Error('Missing file or user');
  }
  if (storageName.startsWith('etl:')) {
    const previewRes = await authFetch(`${getPublicApiUrl()}/api/v1/files/dataset-preview`, {
      body: { user_id: userId, file_name: storageName, max_rows: maxRows },
    });
    const preview = await previewRes.json().catch(() => ({}));
    if (!previewRes.ok) {
      throw new Error(preview.detail || 'Could not prepare ETL dataset preview');
    }
    return includeJsonPaths
      ? { rows: sliceSample(preview.rows, maxRows), jsonPaths: [], selectedJsonPath: null }
      : sliceSample(preview.rows, maxRows);
  }
  const ext = storageName.split('.').pop()?.toLowerCase() || '';

  // JSON can be much larger than a browser-safe preview. Let the backend stream
  // it from Storage and return only paths plus a small row sample.
  if (ext === 'json') {
    const previewRes = await authFetch(`${getPublicApiUrl()}/api/v1/files/json-mapping-preview`, {
      body: { user_id: userId, file_name: storageName, json_path: jsonPath, max_rows: maxRows },
    });
    if (!previewRes.ok) {
      const detail = await previewRes.json().catch(() => ({}));
      throw new Error(detail.detail || 'Could not prepare JSON mapping preview');
    }
    const preview = await previewRes.json();
    return includeJsonPaths
      ? { rows: sliceSample(preview.rows, maxRows), jsonPaths: preview.json_paths || [], selectedJsonPath: preview.selected_json_path || null }
      : sliceSample(preview.rows, maxRows);
  }

  const { data: signedData, error } = await supabase.storage
    .from('business-data')
    .createSignedUrl(`${userId}/${storageName}`, 60);
  if (error) throw error;
  if (!signedData?.signedUrl) throw new Error('Could not create download URL');

  const res = await fetch(signedData.signedUrl);
  if (!res.ok) {
    throw new Error(`Download failed (${res.status})`);
  }

  const contentLength = Number(res.headers.get('content-length') || 0);

  if (ext === 'csv' || ext === 'ndjson') {
    const buf = await res.arrayBuffer();
    const slice = buf.byteLength > MAX_SAMPLE_BYTES ? buf.slice(0, MAX_SAMPLE_BYTES) : buf;
    const text = decodeCsvBytes(slice);
    const raw = Papa.parse(text, { header: false, skipEmptyLines: true });
    const headerRow = detectHeaderRow(raw.data);
    return sliceSample(rowsFromMatrix(raw.data, headerRow), maxRows);
  }

  if (ext === 'xlsx' || ext === 'xls') {
    if (contentLength > MAX_EXCEL_SAMPLE_BYTES) {
      throw new Error('Excel file too large for preview (max 25 MB). Use Parquet or CSV.');
    }
    const workbook = await readXlsxFile(await res.arrayBuffer());
    const sheet = selectWorkbookSheet(workbook);
    if (!sheet) throw new Error('Workbook has no sheets');
    const matrix = sheet.data;
    const headerRow = detectHeaderRow(matrix);
    const rows = rowsFromMatrix(matrix, headerRow);
    return sliceSample(rows, maxRows);
  }

  if (ext === 'parquet') {
    const backendRes = await authFetch(`${getPublicApiUrl()}/api/preview-parquet`, {
      body: { url: signedData.signedUrl },
    });
    if (!backendRes.ok) {
      throw new Error('Failed to parse Parquet on server');
    }
    const jsonRes = await backendRes.json();
    return sliceSample(jsonRes.data, maxRows);
  }

  throw new Error(`Unsupported file type: ${ext}`);
}
