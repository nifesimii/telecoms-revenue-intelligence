// Single chat message bubble.
//
// User msg     → right-aligned, MTN yellow (#FFCB00) background, dark text
// Assistant    → left-aligned, white background, subtle border
//                Markdown rendered (bold, lists, line breaks, tables) via
//                react-markdown + remark-gfm. NGN amounts get a darker weight.
//                Tools_called rendered as small grey pills below the body.
//                If get_dealer_summary or get_orsc_summary was called, a
//                compact "top 10 by commission" mini-table renders below.
// Loading      → an isolated assistant-styled bubble with three bouncing dots.

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { formatNGN, formatPeriod, NGN_RE, NGN_MATCH_RE } from '../lib/format.js';

// ---------------------------------------------------------------------------
// Currency highlighter — wraps "NGN X[,XXX].XX" matches in a bolder span.
// Mirrors the agent's KB-mandated output format (see CLAUDE.md).
// Applied via custom react-markdown component overrides for p / li / td / strong.
// ---------------------------------------------------------------------------

function enhanceText(node) {
  if (typeof node === 'string') {
    if (!node.includes('NGN')) return node;
    const parts = node.split(NGN_RE);
    return parts.map((part, i) =>
      NGN_MATCH_RE.test(part) ? (
        <span key={i} className="font-bold text-gray-900">
          {part}
        </span>
      ) : (
        part
      ),
    );
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => (
      <React.Fragment key={i}>{enhanceText(child)}</React.Fragment>
    ));
  }
  return node;
}

const mdComponents = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{enhanceText(children)}</p>,
  ul: ({ children }) => (
    <ul className="list-disc ml-5 mb-2 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal ml-5 mb-2 space-y-0.5">{children}</ol>
  ),
  li: ({ children }) => <li>{enhanceText(children)}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-gray-900">
      {enhanceText(children)}
    </strong>
  ),
  em: ({ children }) => <em className="italic">{enhanceText(children)}</em>,
  h1: ({ children }) => (
    <h1 className="text-lg font-semibold mt-3 mb-2">{enhanceText(children)}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-semibold mt-3 mb-2">
      {enhanceText(children)}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold mt-2 mb-1">{enhanceText(children)}</h3>
  ),
  hr: () => <hr className="my-3 border-gray-200" />,
  table: ({ children }) => (
    <div className="overflow-x-auto my-3">
      <table className="text-xs border-collapse border border-gray-200 w-full">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-100">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  th: ({ children }) => (
    <th className="border border-gray-200 px-2 py-1 text-left font-semibold text-gray-700">
      {enhanceText(children)}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-gray-200 px-2 py-1 align-top">
      {enhanceText(children)}
    </td>
  ),
  code: ({ children }) => (
    <code className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">
      {children}
    </code>
  ),
};

// ---------------------------------------------------------------------------
// Mini data table — top 10 dealers by commission (dev_act) or subscription
// amount (orsc). Rendered below assistant text when applicable.
// ---------------------------------------------------------------------------

function MiniDealerTable({ rows, valueKey, valueHeader, countKey, countHeader, period }) {
  const top = [...rows]
    .sort((a, b) => (b[valueKey] || 0) - (a[valueKey] || 0))
    .slice(0, 10);
  if (top.length === 0) return null;
  return (
    <div className="mt-3 overflow-x-auto">
      {period && (
        <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">
          Top 10 by {valueHeader.toLowerCase()} · {formatPeriod(period)}
        </div>
      )}
      <table className="text-xs border-collapse border border-gray-200 w-full">
        <thead className="bg-gray-100 text-gray-700">
          <tr>
            <th className="border border-gray-200 px-2 py-1 text-left">#</th>
            <th className="border border-gray-200 px-2 py-1 text-left">Dealer</th>
            <th className="border border-gray-200 px-2 py-1 text-right">
              {countHeader}
            </th>
            <th className="border border-gray-200 px-2 py-1 text-right">
              {valueHeader}
            </th>
          </tr>
        </thead>
        <tbody>
          {top.map((r, i) => (
            <tr key={r.dealer_id || i} className="hover:bg-gray-50">
              <td className="border border-gray-200 px-2 py-1 text-gray-500">
                {i + 1}
              </td>
              <td
                className="border border-gray-200 px-2 py-1 truncate max-w-[200px]"
                title={r.dealer_name}
              >
                {r.dealer_name}
              </td>
              <td className="border border-gray-200 px-2 py-1 text-right tabular-nums">
                {r[countKey] ?? 0}
              </td>
              <td className="border border-gray-200 px-2 py-1 text-right tabular-nums font-semibold text-gray-900">
                {formatNGN(r[valueKey])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pickDealerMiniTable(tools_called, raw_data, period) {
  if (!raw_data) return null;
  if (tools_called?.includes('get_dealer_summary')) {
    const rows = raw_data['get_dealer_summary']?.rows || [];
    return (
      <MiniDealerTable
        rows={rows}
        valueKey="total_commission_ngn"
        valueHeader="Commission"
        countKey="total_activations"
        countHeader="Activations"
        period={period}
      />
    );
  }
  if (tools_called?.includes('get_orsc_summary')) {
    const rows = raw_data['get_orsc_summary']?.rows || [];
    return (
      <MiniDealerTable
        rows={rows}
        valueKey="total_subscription_amount_ngn"
        valueHeader="Subscription"
        countKey="device_count"
        countHeader="Devices"
        period={period}
      />
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Tool pills
// ---------------------------------------------------------------------------

function ToolPills({ tools_called, period }) {
  if (!tools_called || tools_called.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      {tools_called.map((name, i) => (
        <span
          key={`${name}-${i}`}
          className="inline-block bg-gray-100 text-gray-600 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border border-gray-200"
        >
          {name}
        </span>
      ))}
      {period && (
        <span className="text-[10px] text-gray-500">· {formatPeriod(period)}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading dots — for the placeholder bubble while isLoading
// ---------------------------------------------------------------------------

export function LoadingBubble() {
  return (
    <div className="flex justify-start mb-3">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
        <div className="flex items-end gap-1.5 h-4">
          <span
            className="w-2 h-2 bg-gray-400 rounded-full bubble-bounce"
            style={{ animationDelay: '0ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full bubble-bounce"
            style={{ animationDelay: '180ms' }}
          />
          <span
            className="w-2 h-2 bg-gray-400 rounded-full bubble-bounce"
            style={{ animationDelay: '360ms' }}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main bubble
// ---------------------------------------------------------------------------

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const miniTable = !isUser
    ? pickDealerMiniTable(message.tools_called, message.raw_data, message.mon_period)
    : null;

  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[80%] bg-mtn-yellow text-gray-900 rounded-2xl rounded-br-md px-4 py-2.5 shadow-sm whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[90%] bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm text-sm text-gray-800 leading-relaxed">
        <ToolPills tools_called={message.tools_called} period={message.mon_period} />
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {message.content || ''}
        </ReactMarkdown>
        {miniTable}
      </div>
    </div>
  );
}
