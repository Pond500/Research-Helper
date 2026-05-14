'use client';

import { useState } from 'react';
import { Send, Square } from 'lucide-react';

type ChatInputProps = {
  inProgress: boolean;
  onSend: (message: string) => void | Promise<void>;
  chatReady: boolean;
  onStop?: () => void;
  hideStopButton?: boolean;
};

export function ChatInputWithModelSelector({
  inProgress,
  onSend,
  chatReady,
  onStop,
  hideStopButton,
}: ChatInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !inProgress) {
      await onSend(message);
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-3 border-t border-border bg-background">
      <div
        className={`flex items-center gap-2 bg-card rounded-2xl border px-3 py-2 shadow-sm transition-all duration-200 ${
          inProgress ? 'border-primary/40' : 'border-border focus-within:border-primary focus-within:shadow-md focus-within:shadow-primary/10'
        }`}
      >
        {/* Text input */}
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={inProgress ? 'Agent is working…' : 'Ask a research question…'}
          disabled={inProgress || !chatReady}
          className="flex-1 text-sm outline-none bg-transparent text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed min-w-0"
        />

        {/* Action button */}
        {!inProgress ? (
          <button
            type="submit"
            disabled={!message.trim() || !chatReady}
            className="flex-shrink-0 w-8 h-8 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-150 shadow-sm"
            aria-label="Send"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        ) : (
          !hideStopButton && onStop && (
            <button
              type="button"
              onClick={onStop}
              className="flex-shrink-0 w-8 h-8 rounded-xl bg-destructive text-destructive-foreground flex items-center justify-center hover:bg-destructive/90 transition-all duration-150 shadow-sm"
              aria-label="Stop"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          )
        )}
      </div>
    </form>
  );
}
