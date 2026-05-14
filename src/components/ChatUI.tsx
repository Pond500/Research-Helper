'use client';

import React, { useEffect, useRef } from 'react';
import { ChatMessage } from '@/lib/useAgentStream';
import { Resource } from '@/lib/types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { DataSourceToggle } from './DataSourceToggle';
import { ChatInputWithModelSelector } from './ChatInputWithModelSelector';
import { Resources } from './Resources';
import { Trash2, AlertCircle, CheckCircle2, FileText } from 'lucide-react';

type Suggestion = { title: string; message: string };

type ChatUIProps = {
  messages: ChatMessage[];
  isRunning: boolean;
  hasReport: boolean;
  pendingDeleteUrls: string[] | null;
  onSend: (message: string) => void;
  onStop: () => void;
  onConfirmDelete: (confirmed: boolean) => void;
  suggestions?: Suggestion[];
  activeSources: string[];
  onSourcesChange: (sources: string[]) => void;
  resources: Resource[];
};

function isInternalMessage(msg: ChatMessage): boolean {
  if (msg.role !== 'assistant') return false;
  const content = msg.content.trim();
  if (content === '') return true;
  if (content.startsWith('{') && content.endsWith('}')) {
    try { JSON.parse(content); return true; } catch { /* not JSON */ }
  }
  return false;
}

export function ChatUI({
  messages,
  isRunning,
  hasReport,
  pendingDeleteUrls,
  onSend,
  onStop,
  onConfirmDelete,
  suggestions = [],
  activeSources,
  onSourcesChange,
  resources,
}: ChatUIProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingDeleteUrls]);

  const visibleMessages = messages.filter((m) => !isInternalMessage(m));
  const isEmpty = visibleMessages.length === 0;
  const lastVisible = visibleMessages[visibleMessages.length - 1];
  const showTyping = isRunning && lastVisible?.role === 'user';
  const showCompletionCard =
    hasReport && !isRunning && lastVisible?.role === 'user' && visibleMessages.some((m) => m.role === 'user');

  return (
    <div className="h-full flex flex-col overflow-hidden bg-secondary/30">
      {/* Source toggles */}
      <DataSourceToggle activeSources={activeSources} onSourcesChange={onSourcesChange} />

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {isEmpty ? (
          /* Empty state — suggestions */
          <div className="flex flex-col h-full justify-end pb-2">
            <p className="text-sm font-medium text-foreground/70 mb-3">
              What would you like to research?
            </p>
            <div className="space-y-2">
              {suggestions.map((s) => (
                <button
                  key={s.title}
                  onClick={() => !isRunning && onSend(s.message)}
                  disabled={isRunning}
                  className="w-full text-left px-4 py-3 bg-card rounded-2xl border border-border hover:border-primary/40 hover:shadow-sm transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed group"
                >
                  <div className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                    {s.title}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                    {s.message}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {visibleMessages.map((msg) => {
              if (msg.role === 'error') {
                return (
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-[85%] flex items-start gap-2.5 px-4 py-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-2xl rounded-bl-sm text-sm shadow-sm">
                      <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      <span>{msg.content}</span>
                    </div>
                  </div>
                );
              }
              return (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] px-4 py-3 text-sm leading-relaxed shadow-sm ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground rounded-2xl rounded-br-sm'
                        : 'bg-card border border-border text-foreground rounded-2xl rounded-bl-sm'
                    }`}
                  >
                    {msg.role === 'assistant' ? (
                      <MarkdownRenderer content={msg.content} />
                    ) : (
                      <span>{msg.content}</span>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Completion card */}
            {showCompletionCard && (
              <div className="flex justify-start">
                <div className="max-w-[85%] bg-card border border-green-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-2 mb-1.5">
                    <div className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
                      <CheckCircle2 className="w-3 h-3 text-green-600" />
                    </div>
                    <span className="text-sm font-semibold text-green-700">รายงานพร้อมแล้ว</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <FileText className="w-3 h-3 flex-shrink-0" />
                    <span>
                      ดูรายงานฉบับเต็มได้ที่แท็บ{' '}
                      <span className="font-medium text-foreground">Report</span>{' '}
                      ด้านขวา
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Typing indicator */}
            {showTyping && (
              <div className="flex justify-start">
                <div className="bg-card border border-border rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground dot-1" />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground dot-2" />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground dot-3" />
                </div>
              </div>
            )}

            {/* Delete confirmation */}
            {pendingDeleteUrls !== null && (
              <div className="bg-card border border-border rounded-2xl p-4 shadow-sm">
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-8 h-8 rounded-xl bg-destructive/10 flex items-center justify-center flex-shrink-0">
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground">Delete resources?</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {pendingDeleteUrls.length} resource{pendingDeleteUrls.length !== 1 ? 's' : ''} will be removed
                    </div>
                  </div>
                </div>
                {pendingDeleteUrls.length > 0 && (
                  <div className="mb-3">
                    <Resources
                      resources={resources.filter((r) => pendingDeleteUrls.includes(r.url))}
                      customWidth={180}
                    />
                  </div>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => onConfirmDelete(false)}
                    className="flex-1 py-2 text-sm font-medium border border-border rounded-xl text-foreground hover:bg-secondary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => onConfirmDelete(true)}
                    className="flex-1 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-xl hover:bg-destructive/90 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <ChatInputWithModelSelector
        inProgress={isRunning}
        onSend={onSend}
        chatReady={!isRunning || pendingDeleteUrls !== null}
        onStop={onStop}
        hideStopButton={false}
      />
    </div>
  );
}
