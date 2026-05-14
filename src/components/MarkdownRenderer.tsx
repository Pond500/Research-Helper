"use client";

import React, { useCallback, useEffect, useRef, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import EChartsViewer from "./EChartsViewer";
import type { ChartSpec, Citation } from "@/lib/types";

interface MarkdownRendererProps {
  content: string;
  charts?: ChartSpec[];
  citations?: Record<string, Citation>;
}

function extractIframeSrc(html: string): string | null {
  const srcMatch = html.match(/src=["']([^"']+)["']/);
  return srcMatch ? srcMatch[1] : null;
}

function generateEmbedId(src: string): string {
  try {
    const url = new URL(src);
    return `embed-${url.pathname.replace(/[^a-zA-Z0-9]/g, "-")}`;
  } catch {
    return `embed-${src.replace(/[^a-zA-Z0-9]/g, "-").slice(0, 50)}`;
  }
}

const markdownComponents = {
  h1: (props: React.ComponentPropsWithoutRef<"h1">) => (
    <h1 className="text-3xl font-bold mb-4 text-primary" {...props} />
  ),
  h2: (props: React.ComponentPropsWithoutRef<"h2">) => (
    <h2 className="text-2xl font-semibold mb-3 mt-6 text-primary" {...props} />
  ),
  h3: (props: React.ComponentPropsWithoutRef<"h3">) => (
    <h3 className="text-xl font-semibold mb-2 mt-4 text-primary" {...props} />
  ),
  p: (props: React.ComponentPropsWithoutRef<"p">) => (
    <p className="mb-4 text-foreground leading-relaxed" {...props} />
  ),
  ul: (props: React.ComponentPropsWithoutRef<"ul">) => (
    <ul className="list-disc list-inside mb-4 space-y-2" {...props} />
  ),
  ol: (props: React.ComponentPropsWithoutRef<"ol">) => (
    <ol className="list-decimal list-inside mb-4 space-y-2" {...props} />
  ),
  li: (props: React.ComponentPropsWithoutRef<"li">) => (
    <li className="text-foreground" {...props} />
  ),
  a: (props: React.ComponentPropsWithoutRef<"a">) => (
    <a
      className="text-[#6766FC] hover:underline"
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    />
  ),
  code: ({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) => {
    const isCodeBlock = className?.includes("language-");
    if (!isCodeBlock) {
      return (
        <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="block bg-gray-100 p-4 rounded-lg text-sm font-mono overflow-x-auto mb-4" {...props}>
        {children}
      </code>
    );
  },
  table: (props: React.ComponentPropsWithoutRef<"table">) => (
    <div className="overflow-x-auto my-5 rounded-xl border border-gray-200 shadow-sm">
      <table className="w-full text-sm border-collapse" {...props} />
    </div>
  ),
  thead: (props: React.ComponentPropsWithoutRef<"thead">) => (
    <thead className="bg-indigo-50" {...props} />
  ),
  tbody: (props: React.ComponentPropsWithoutRef<"tbody">) => (
    <tbody className="divide-y divide-gray-100" {...props} />
  ),
  tr: (props: React.ComponentPropsWithoutRef<"tr">) => (
    <tr className="transition-colors hover:bg-gray-50/70" {...props} />
  ),
  th: (props: React.ComponentPropsWithoutRef<"th">) => (
    <th
      className="px-4 py-2.5 text-left text-xs font-semibold text-indigo-700 uppercase tracking-wider whitespace-nowrap border-b border-indigo-100"
      {...props}
    />
  ),
  td: (props: React.ComponentPropsWithoutRef<"td">) => (
    <td className="px-4 py-2.5 text-foreground border-b border-gray-100 last:border-b-0" {...props} />
  ),
};

const iframeRegistry = new Map<string, string>();

/** Replace [N] citation markers with <cite data-n="N"></cite> for rehypeRaw to pick up */
function injectCitationTags(text: string): string {
  return text.replace(/\[(\d+)\](?!\()/g, '<cite data-n="$1"></cite>');
}

type ContentSegment =
  | { type: "text"; content: string; key: string }
  | { type: "iframe"; id: string; src: string; key: string }
  | { type: "chart"; chartId: string; key: string };

export function MarkdownRenderer({ content, charts = [], citations = {} }: MarkdownRendererProps) {
  const chartMap = useMemo(() => {
    const m = new Map<string, ChartSpec>();
    for (const c of charts) m.set(c.id, c);
    return m;
  }, [charts]);

  const citationMap = useMemo(() => {
    const m = new Map<string, Citation>();
    for (const [k, v] of Object.entries(citations)) m.set(k, v);
    return m;
  }, [citations]);

  // Build markdown components inside the render so cite can close over citationMap
  const components = useMemo(() => ({
    ...markdownComponents,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars
    cite: ({ node, ...props }: any) => {
      const n: string = props["data-n"] ?? "";
      return <CitationBadge number={n} citation={citationMap.get(n)} />;
    },
  }), [citationMap]);

  const segments = useMemo(() => {
    // Combined pattern: iframes and [CHART:id] markers
    const combinedPattern = /(<iframe[\s\S]*?<\/iframe>|\[CHART:[a-zA-Z0-9_-]+\])/gi;
    const parts: ContentSegment[] = [];
    let lastIndex = 0;
    let textIdx = 0;
    let match: RegExpExecArray | null;

    while ((match = combinedPattern.exec(content)) !== null) {
      if (match.index > lastIndex) {
        const textContent = content.slice(lastIndex, match.index);
        if (textContent.trim()) {
          parts.push({ type: "text", content: textContent, key: `text-${textIdx++}` });
        }
      }

      const token = match[0];
      if (token.startsWith("<iframe")) {
        const src = extractIframeSrc(token);
        if (src) {
          const id = generateEmbedId(src);
          if (!iframeRegistry.has(id)) iframeRegistry.set(id, src);
          parts.push({ type: "iframe", id, src, key: id });
        }
      } else {
        // [CHART:some-id]
        const chartId = token.slice(7, -1); // strip [CHART: and ]
        parts.push({ type: "chart", chartId, key: `chart-${chartId}` });
      }

      lastIndex = combinedPattern.lastIndex;
    }

    if (lastIndex < content.length) {
      const textContent = content.slice(lastIndex);
      if (textContent.trim()) {
        parts.push({ type: "text", content: textContent, key: `text-${textIdx}` });
      }
    }

    return parts;
  }, [content]);

  return (
    <div className="prose prose-slate max-w-none bg-background px-6 py-8 border-0 shadow-none rounded-xl">
      {segments.map((segment) => {
        if (segment.type === "text") {
          return (
            <ReactMarkdown
              key={segment.key}
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={components}
            >
              {injectCitationTags(segment.content)}
            </ReactMarkdown>
          );
        }
        if (segment.type === "chart") {
          const chart = chartMap.get(segment.chartId);
          if (!chart) return <ChartSkeleton key={segment.key} />;
          return <EChartsViewer key={segment.key} chart={chart} />;
        }
        // iframe (legacy Tako embeds)
        const registeredSrc = iframeRegistry.get(segment.id);
        if (!registeredSrc) return null;
        return <StableIframe key={segment.key} id={segment.id} src={registeredSrc} />;
      })}
    </div>
  );
}

function CitationBadge({ number, citation }: { number: string; citation?: Citation }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setPos({
        top: rect.bottom + window.scrollY + 6,
        left: Math.min(rect.left + window.scrollX - 8, window.innerWidth - 320),
      });
    }
    setOpen((v) => !v);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  if (!citation) {
    return <sup className="text-gray-400 text-[10px] ml-0.5">[{number}]</sup>;
  }

  let hostname = "";
  try { hostname = new URL(citation.url).hostname.replace("www.", ""); } catch { /* ignore */ }

  return (
    <>
      <sup>
        <button
          ref={btnRef}
          onClick={handleClick}
          className="inline-flex items-center justify-center min-w-[16px] h-4 px-1 text-[9px] font-bold text-white bg-indigo-500 hover:bg-indigo-600 rounded-full ml-0.5 cursor-pointer transition-colors align-super leading-none"
        >
          {number}
        </button>
      </sup>

      {open && typeof document !== "undefined" && createPortal(
        <div
          style={{ position: "absolute", top: pos.top, left: pos.left, zIndex: 9999 }}
          className="w-80 bg-white border border-gray-200 rounded-xl shadow-2xl p-3 text-left"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start gap-2.5 mb-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`https://www.google.com/s2/favicons?domain=${hostname}&sz=32`}
              alt=""
              className="w-4 h-4 mt-0.5 rounded flex-shrink-0"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
            <div className="min-w-0">
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-semibold text-gray-900 hover:text-indigo-600 hover:underline line-clamp-1 block"
              >
                {citation.title || hostname}
              </a>
              <span className="text-[10px] text-gray-400 truncate block">{hostname}</span>
            </div>
          </div>
          {/* Excerpt */}
          {citation.snippet && (
            <p className="text-[11px] text-gray-600 leading-relaxed line-clamp-4 border-t border-gray-100 pt-2">
              {citation.snippet}
            </p>
          )}
          {/* Open link */}
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 flex items-center gap-1 text-[10px] text-indigo-500 hover:text-indigo-700 font-medium"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            เปิดแหล่งข้อมูล
          </a>
        </div>,
        document.body
      )}
    </>
  );
}

function ChartSkeleton() {
  return (
    <div className="relative rounded-xl overflow-hidden border border-gray-200 bg-white my-3 shadow-sm">
      {/* Header shimmer */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50/80">
        <div className="h-3.5 w-40 rounded-md bg-gray-200 animate-pulse" />
        <div className="flex items-center gap-1">
          <div className="w-7 h-7 rounded-lg bg-gray-200 animate-pulse" />
          <div className="w-7 h-7 rounded-lg bg-gray-200 animate-pulse" />
          <div className="w-7 h-7 rounded-lg bg-gray-200 animate-pulse" />
        </div>
      </div>
      {/* Body shimmer */}
      <div className="bg-white" style={{ height: "340px" }}>
        <div className="h-full w-full flex flex-col items-center justify-center gap-4 px-6">
          {/* Fake axis area */}
          <div className="w-full flex items-end gap-2 px-4" style={{ height: "200px" }}>
            {[55, 80, 45, 90, 65, 75, 50, 85, 60, 70].map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-t-sm bg-gray-200 animate-pulse"
                style={{ height: `${h}%`, animationDelay: `${i * 60}ms` }}
              />
            ))}
          </div>
          {/* Loading label */}
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-indigo-300 animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="w-2 h-2 rounded-full bg-indigo-300 animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="w-2 h-2 rounded-full bg-indigo-300 animate-bounce" style={{ animationDelay: "300ms" }} />
            <span className="text-xs text-gray-400 ml-1">กำลังสร้างกราฟ…</span>
          </div>
        </div>
      </div>
    </div>
  );
}

const StableIframe = React.memo(
  function StableIframe({ src }: { id: string; src: string }) {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    useEffect(() => {
      const handleResize = (event: MessageEvent) => {
        if (event.data?.type !== "tako::resize") return;
        if (iframeRef.current?.contentWindow === event.source) {
          iframeRef.current.style.height = `${event.data.height}px`;
        }
      };
      window.addEventListener("message", handleResize);
      return () => window.removeEventListener("message", handleResize);
    }, []);

    return (
      <iframe
        ref={iframeRef}
        src={src}
        className="w-full border-0 rounded-lg"
        style={{ height: "400px", display: "block" }}
        scrolling="no"
        frameBorder="0"
        allow="fullscreen"
        data-tako-embed="true"
      />
    );
  },
  (prevProps, nextProps) => prevProps.id === nextProps.id && prevProps.src === nextProps.src
);
