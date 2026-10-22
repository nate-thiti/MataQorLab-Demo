import { fixMarkdownTables } from './messageContent.js';

const parseTableCells = (line) => {
  const trimmed = line.trim();
  if (!trimmed) return [];
  const normalized = trimmed.startsWith('|') ? trimmed : `| ${trimmed}`;
  const withEnd = normalized.endsWith('|') ? normalized : `${normalized} |`;
  return withEnd
    .split('|')
    .map((c) => c.trim())
    .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
};

const isSeparatorRow = (cells) =>
  cells.length > 0 && cells.every((cell) => /^:?-{2,}:?$/.test(cell));

const isJunkRow = (cells) =>
  cells.length > 0 &&
  cells.every((cell) => !cell || /^[:.\-–—\s]+$/.test(cell));

export function parseMarkdownToBlocks(text) {
  if (!text) return [];
  const normalized = fixMarkdownTables(text);
  const lines = normalized.split('\n');
  const blocks = [];
  let currentTable = null;
  let currentText = [];

  const flushText = () => {
    if (currentText.length > 0) {
      blocks.push({ type: 'markdown', content: currentText.join('\n') });
      currentText = [];
    }
  };

  const flushTable = () => {
    if (!currentTable) return;
    const colCount = Math.max(
      currentTable.headers.length,
      ...currentTable.rows.map((r) => r.length),
      1,
    );
    const pad = (row) => {
      const next = [...row];
      while (next.length < colCount) next.push('');
      return next;
    };
    blocks.push({
      type: 'table',
      headers: pad(currentTable.headers),
      aligns: currentTable.aligns.length ? pad(currentTable.aligns) : Array(colCount).fill('left'),
      rows: currentTable.rows.map(pad),
    });
    currentTable = null;
  };

  for (let i = 0; i < lines.length; i += 1) {
    const trimmed = lines[i].trim();
    const cells = parseTableCells(trimmed);
    const isTableRow = cells.length >= 2 && !trimmed.startsWith('```');

    if (isTableRow) {
      flushText();
      const isSeparator = isSeparatorRow(cells);

      if (!currentTable) {
        currentTable = { headers: cells, aligns: [], rows: [] };
      } else if (isSeparator) {
        currentTable.aligns = cells.map((cell) => {
          if (cell.startsWith(':') && cell.endsWith(':')) return 'center';
          if (cell.endsWith(':')) return 'right';
          return 'left';
        });
      } else if (!isJunkRow(cells)) {
        currentTable.rows.push(cells);
      }
    } else {
      flushTable();
      currentText.push(lines[i]);
    }
  }

  flushText();
  flushTable();

  return blocks;
}
