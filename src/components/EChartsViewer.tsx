"use client";

import React, { useCallback, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { ECharts } from "echarts";
import type { ChartSpec } from "@/lib/types";

// Minimal dark-mode override — Python already generates dark theme colors.
// We only force transparent bg and ensure toolbox/tooltip colours survive the
// applyBrandTheme step in the old code path (now removed).
function withDarkShell(option: Record<string, unknown>): Record<string, unknown> {
  return {
    ...option,
    backgroundColor: "transparent",
  };
}

interface Props {
  chart: ChartSpec;
  compact?: boolean;
}

export default function EChartsViewer({ chart, compact = false }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const chartRef = useRef<{ getEchartsInstance: () => ECharts } | null>(null);

  const option = withDarkShell(chart.option);
  const height = compact ? "220px" : expanded ? "500px" : "340px";

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  const download = useCallback(() => {
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;
    const url = instance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#0F172A" });
    const a = document.createElement("a");
    a.href = url;
    a.download = `${chart.title.replace(/\s+/g, "_")}.png`;
    a.click();
  }, [chart.title]);

  const ChartCanvas = (
    <ReactECharts
      ref={chartRef as React.Ref<ReactECharts>}
      option={option}
      style={{ height: "100%", width: "100%" }}
      opts={{ renderer: "canvas" }}
      notMerge
      lazyUpdate
    />
  );

  return (
    <>
      <div className="relative rounded-xl overflow-hidden border border-gray-200 bg-white my-3 shadow-sm group">
        {/* header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50/80">
          <span className="text-sm font-semibold text-gray-800 truncate pr-4">{chart.title}</span>

          <div className="flex items-center gap-1 shrink-0">
            {/* Download */}
            <button
              onClick={download}
              title="Download PNG"
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-indigo-500 hover:bg-indigo-50 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </button>

            {/* Fullscreen */}
            <button
              onClick={() => setFullscreen(true)}
              title="Fullscreen"
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-indigo-500 hover:bg-indigo-50 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
              </svg>
            </button>

            {/* Expand/collapse */}
            <button
              onClick={toggle}
              title={expanded ? "Collapse" : "Expand"}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-indigo-500 hover:bg-indigo-50 transition-colors"
            >
              {expanded ? (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* chart body */}
        <div className="bg-white transition-all duration-300 ease-in-out" style={{ height }}>
          {ChartCanvas}
        </div>

        {/* source footer */}
        {chart.source && (
          <div className="px-4 py-1.5 border-t border-gray-100 text-[10px] text-gray-400 flex items-center gap-1">
            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {chart.source}
          </div>
        )}
      </div>

      {/* Fullscreen modal */}
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex flex-col"
          onClick={() => setFullscreen(false)}
        >
          <div
            className="flex items-center justify-between px-6 py-3 border-b border-gray-200 bg-white shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="text-base font-semibold text-gray-900">{chart.title}</span>
            <div className="flex items-center gap-2">
              <button
                onClick={download}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download PNG
              </button>
              <button
                onClick={() => setFullscreen(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
          <div className="flex-1 p-4 bg-white" onClick={(e) => e.stopPropagation()}>
            <ReactECharts
              option={option}
              style={{ height: "100%", width: "100%" }}
              opts={{ renderer: "canvas" }}
              notMerge
            />
          </div>
          {chart.source && (
            <div className="px-6 py-2 border-t border-gray-100 text-[10px] text-gray-400 bg-white shrink-0">
              Source: {chart.source}
            </div>
          )}
        </div>
      )}
    </>
  );
}
