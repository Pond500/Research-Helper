'use client';

import { useState } from 'react';
import { CheckIcon, Loader2, ChevronDown } from 'lucide-react';

type Log = { message: string; done: boolean };

const STEP_LABELS: Record<string, string> = {
  download: 'Preparing resources',
  chat_node: 'Analyzing query',
  search_node: 'Searching the web',
  critic_node: 'Reviewing draft quality',
  delete_node: 'Processing deletion',
  perform_delete_node: 'Applying changes',
};

function cleanMessage(msg: string): string {
  return msg.replace(/https?:\/\/([^\s/]+)[^\s]*/g, (_, host) => host);
}

export function LiveActivityFeed({
  logs,
  isRunning,
  currentStep,
}: {
  logs: Log[];
  isRunning: boolean;
  currentStep?: string;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!isRunning && logs.length === 0) return null;

  const stepLabel = currentStep ? (STEP_LABELS[currentStep] ?? currentStep) : null;
  const hasExtra = logs.length > 5;
  const visibleLogs = hasExtra && !expanded ? logs.slice(-5) : logs;
  const activeIndex = visibleLogs.findLastIndex((l) => !l.done);

  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-secondary/40">
        <div className="flex items-center gap-2.5">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              isRunning ? 'bg-primary animate-pulse' : 'bg-emerald-500'
            }`}
          />
          <span className="text-xs font-semibold tracking-widest uppercase text-foreground/70">
            {isRunning ? (stepLabel ?? 'Running…') : 'Complete'}
          </span>
        </div>
        {hasExtra && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? 'Show less' : `+${logs.length - 5} earlier`}
            <ChevronDown
              className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`}
            />
          </button>
        )}
      </div>

      {/* Log items */}
      <div className="px-3 py-2.5 space-y-0.5">
        {visibleLogs.map((log, i) => {
          const isActive = i === activeIndex && !log.done;
          const isPending = !log.done && !isActive;
          return (
            <div
              key={i}
              className={`flex items-start gap-3 px-2 py-1.5 rounded-xl transition-opacity ${
                isPending ? 'opacity-35' : ''
              }`}
            >
              {/* Status dot */}
              <div className="flex-shrink-0 mt-0.5">
                {log.done ? (
                  <div className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center">
                    <CheckIcon className="w-2.5 h-2.5 text-white" strokeWidth={3} />
                  </div>
                ) : isActive ? (
                  <div className="w-4 h-4 rounded-full bg-primary flex items-center justify-center">
                    <Loader2 className="w-2.5 h-2.5 text-white animate-spin" />
                  </div>
                ) : (
                  <div className="w-4 h-4 rounded-full border-2 border-border" />
                )}
              </div>

              {/* Message */}
              <span
                className={`text-xs leading-relaxed ${
                  log.done
                    ? 'text-muted-foreground'
                    : isActive
                    ? 'text-foreground font-medium'
                    : 'text-muted-foreground'
                }`}
              >
                {cleanMessage(log.message)}
              </span>
            </div>
          );
        })}

        {/* Empty running state */}
        {isRunning && logs.length === 0 && (
          <div className="flex items-center gap-3 px-2 py-1.5">
            <Loader2 className="w-4 h-4 text-primary animate-spin flex-shrink-0" />
            <span className="text-xs text-muted-foreground">Initializing…</span>
          </div>
        )}
      </div>
    </div>
  );
}
