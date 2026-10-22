// @ts-nocheck
import { useEffect, useRef, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { parseMarkdownToBlocks } from './markdownBlocks.js';

const CellMarkdown = ({ cell, components, isHeader = false }) => {
  const trimmed = (cell || '').trim();
  const pctMatch = !isHeader && trimmed.match(/^([+-]?\d+(?:[.,]\d+)?)\s*%$/);

  if (pctMatch) {
    const value = parseFloat(pctMatch[1].replace(',', '.'));
    const colorClass =
      value > 0
        ? 'text-emerald-600 dark:text-emerald-400 font-semibold'
        : value < 0
          ? 'text-rose-600 dark:text-rose-400 font-semibold'
          : 'text-gray-600 dark:text-zinc-400';
    return (
      <span className={colorClass}>
        {value > 0 ? `+${pctMatch[1]}%` : `${pctMatch[1]}%`}
      </span>
    );
  }

  return (
    <ReactMarkdown
      components={{
        ...components,
        p: ({ children }) => <span>{children}</span>,
      }}
    >
      {trimmed}
    </ReactMarkdown>
  );
};

const RenderTableBlock = ({ headers, aligns, rows, components }) => {
  const isTotalRow = (row) =>
    row.some((cell) => /total|รวม|เฉลี่ย|average/i.test(cell));
  const isNumericCell = (cell) =>
    /^[+\-]?(?:[$฿€£¥]\s*)?[\d,.]+(?:\s*(?:%|บาท|THB|USD|EUR|GBP|JPY))?$/i.test(
      (cell || '').replace(/\*\*/g, '').trim(),
    );
  const cellAlign = (cell, index) =>
    aligns[index] && aligns[index] !== 'left'
      ? aligns[index]
      : isNumericCell(cell)
        ? 'right'
        : 'left';

  return (
    <div className="not-prose my-6 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.06)] dark:border-slate-700/80 dark:bg-slate-900/90">
      <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-separate border-spacing-0 text-sm">
        <thead className="bg-slate-100/90 dark:bg-slate-800/85">
          <tr>
            {headers.map((h, idx) => (
              <th
                key={idx}
                scope="col"
                className="min-w-[9rem] border-b border-slate-200 px-4 py-3.5 text-xs font-semibold leading-snug text-slate-700 first:pl-5 dark:border-slate-700 dark:text-slate-200"
                style={{ textAlign: aligns[idx] || 'left' }}
              >
                <CellMarkdown cell={h} components={components} isHeader />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr
              key={rIdx}
              className={`transition-colors ${
                isTotalRow(row)
                  ? 'bg-amber-50/70 font-semibold dark:bg-amber-950/20'
                  : rIdx % 2
                    ? 'bg-slate-50/55 dark:bg-slate-800/25'
                    : 'bg-white dark:bg-slate-900/70'
              } hover:bg-amber-50/45 dark:hover:bg-amber-950/15`}
            >
              {row.map((cell, cIdx) => (
                <td
                  key={cIdx}
                  className={`border-b border-slate-100 px-4 py-3.5 align-top leading-relaxed text-slate-600 first:pl-5 dark:border-slate-800 dark:text-slate-300 ${
                    cIdx === 0 ? 'font-medium text-slate-800 dark:text-slate-100' : ''
                  } ${isNumericCell(cell) ? 'whitespace-nowrap font-mono text-[13px] tabular-nums' : ''}`}
                  style={{ textAlign: cellAlign(cell, cIdx) }}
                >
                  <CellMarkdown cell={cell} components={components} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
};

const defaultMarkdownComponents = {
  h1: ({ children }) => (
    <h1 className="text-xl font-serif font-bold text-[#1a1a1a] dark:text-slate-100 mt-6 mb-3">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-serif font-bold text-[#1a1a1a] dark:text-slate-100 mt-5 mb-2">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-bold text-[#1a1a1a] dark:text-slate-100 mt-4 mb-2">{children}</h3>
  ),
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 my-3">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 my-3">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  strong: ({ children }) => (
    <strong className="font-bold text-[#1a1a1a] dark:text-slate-100">{children}</strong>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-amber-700 underline decoration-amber-500/35 underline-offset-2 transition-colors hover:text-amber-600 dark:text-amber-400 dark:hover:text-amber-300"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-4 border-amber-400 bg-amber-50/60 px-4 py-2 text-slate-600 dark:bg-amber-950/20 dark:text-slate-300">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-6 border-slate-200 dark:border-slate-700" />,
  code: ({ children }) => (
    <code className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[0.88em] text-rose-700 dark:bg-slate-800 dark:text-rose-300">
      {children}
    </code>
  ),
};

const TypewriterMarkdown = ({
  content = '',
  onComplete,
  components = {},
}) => {
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    onCompleteRef.current?.();
  }, [content]);

  const mergedComponents = useMemo(
    () => ({ ...defaultMarkdownComponents, ...components }),
    [components],
  );

  const blocks = useMemo(
    () => parseMarkdownToBlocks(content),
    [content],
  );

  return (
    <>
      {blocks.map((block, idx) => {
        if (block.type === 'table') {
          return (
            <RenderTableBlock
              key={idx}
              headers={block.headers}
              aligns={block.aligns}
              rows={block.rows}
              components={mergedComponents}
            />
          );
        }
        if (!block.content.trim()) return null;
        return (
          <ReactMarkdown key={idx} components={mergedComponents}>
            {block.content}
          </ReactMarkdown>
        );
      })}
    </>
  );
};

export default TypewriterMarkdown;
