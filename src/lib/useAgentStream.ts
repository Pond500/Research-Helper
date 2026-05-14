'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { AgentState } from './types';

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  toolCalls?: ToolCallRecord[];
};

type ToolCallRecord = {
  id: string;
  name: string;
  args: Record<string, unknown>;
};

type UseAgentStreamOptions = {
  agentUrl: string;
  initialState: Partial<AgentState>;
};

export type UseAgentStreamResult = {
  agentState: AgentState;
  messages: ChatMessage[];
  isRunning: boolean;
  currentStep?: string;
  pendingDeleteUrls: string[] | null;
  sendMessage: (content: string, stateOverride?: Partial<AgentState>) => void;
  confirmDelete: (confirmed: boolean) => void;
  stop: () => void;
  updateAgentState: (updates: Partial<AgentState>) => void;
};

type JsonPatchOp = { op: string; path: string; value?: unknown };

function applyJsonPatch(state: AgentState, ops: JsonPatchOp[]): AgentState {
  const result: Record<string, unknown> = { ...state };
  for (const { op, path, value } of ops) {
    const parts = path.replace(/^\//, '').split('/');
    if (parts.length === 0 || !parts[0]) continue;
    const key = parts[0];
    if (op === 'replace' || op === 'add') {
      if (parts.length === 1) {
        result[key] = value;
      } else if (parts.length === 2 && parts[1] === '-' && Array.isArray(result[key])) {
        result[key] = [...(result[key] as unknown[]), value];
      } else if (parts.length === 2 && Array.isArray(result[key])) {
        const idx = parseInt(parts[1], 10);
        if (!isNaN(idx)) {
          const arr = [...(result[key] as unknown[])];
          if (op === 'add') arr.splice(idx, 0, value);
          else arr[idx] = value;
          result[key] = arr;
        }
      }
    } else if (op === 'remove') {
      if (parts.length === 1) {
        delete result[key];
      } else if (parts.length === 2 && Array.isArray(result[key])) {
        const idx = parseInt(parts[1], 10);
        if (!isNaN(idx)) {
          const arr = [...(result[key] as unknown[])];
          arr.splice(idx, 1);
          result[key] = arr;
        }
      }
    }
  }
  return result as AgentState;
}

const DEFAULT_STATE: AgentState = {
  model: 'openai',
  research_question: '',
  report: '',
  resources: [],
  logs: [],
};

export function useAgentStream({
  agentUrl,
  initialState,
}: UseAgentStreamOptions): UseAgentStreamResult {
  const [agentState, setAgentState] = useState<AgentState>({
    ...DEFAULT_STATE,
    ...initialState,
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | undefined>();
  const [pendingDeleteUrls, setPendingDeleteUrls] = useState<string[] | null>(null);

  const threadIdRef = useRef(`thread-${Date.now()}`);
  const abortRef = useRef<AbortController | null>(null);
  const agentStateRef = useRef(agentState);
  const messagesRef = useRef(messages);

  useEffect(() => { agentStateRef.current = agentState; }, [agentState]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  const runStream = useCallback(
    async (
      messagesToSend: Array<{ id: string; role: string; content: string; tool_call_id?: string }>,
      forwardedProps?: Record<string, unknown>,
      stateOverride?: Partial<AgentState>,
    ) => {
      setIsRunning(true);
      setPendingDeleteUrls(null);
      abortRef.current = new AbortController();

      const currentState = {
        ...agentStateRef.current,
        logs: [],
        ...(stateOverride ?? {}),
      };
      setAgentState(currentState);

      let gotRunFinished = false;
      let currentMsgId = '';
      let currentMsgContent = '';
      let currentToolCallId = '';
      let currentToolCallName = '';
      let currentToolCallArgsStr = '';

      try {
        const res = await fetch(agentUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          body: JSON.stringify({
            thread_id: threadIdRef.current,
            run_id: `run-${Date.now()}`,
            messages: messagesToSend,
            state: currentState,
            tools: [],
            context: [],
            forwarded_props: forwardedProps ?? {},
          }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const ev = JSON.parse(line.slice(6));
              switch (ev.type) {
                case 'TEXT_MESSAGE_START':
                  currentMsgId = ev.messageId ?? `msg-${Date.now()}`;
                  currentMsgContent = '';
                  setMessages((prev) => [
                    ...prev,
                    { id: currentMsgId, role: 'assistant', content: '' },
                  ]);
                  break;

                case 'TEXT_MESSAGE_CONTENT':
                  currentMsgContent += ev.delta ?? '';
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === currentMsgId ? { ...m, content: currentMsgContent } : m,
                    ),
                  );
                  break;

                case 'TOOL_CALL_START':
                  currentToolCallId = ev.toolCallId ?? '';
                  currentToolCallName = ev.toolCallName ?? '';
                  currentToolCallArgsStr = '';
                  break;

                case 'TOOL_CALL_ARGS':
                  currentToolCallArgsStr += ev.delta ?? '';
                  break;

                case 'TOOL_CALL_END':
                  if (currentToolCallId && currentMsgId) {
                    let args: Record<string, unknown> = {};
                    try { args = JSON.parse(currentToolCallArgsStr); } catch { /**/ }
                    const tc: ToolCallRecord = { id: currentToolCallId, name: currentToolCallName, args };
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === currentMsgId
                          ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] }
                          : m,
                      ),
                    );
                    currentToolCallId = '';
                    currentToolCallName = '';
                    currentToolCallArgsStr = '';
                  }
                  break;

                case 'STATE_SNAPSHOT':
                  if (ev.snapshot) {
                    setAgentState((prev) => ({ ...prev, ...ev.snapshot }));
                  }
                  break;

                case 'STATE_DELTA':
                  if (Array.isArray(ev.delta)) {
                    setAgentState((prev) => applyJsonPatch(prev, ev.delta));
                  }
                  break;

                case 'STEP_STARTED':
                  setCurrentStep(ev.stepName);
                  break;

                case 'STEP_FINISHED':
                  setCurrentStep(undefined);
                  break;

                case 'RUN_FINISHED':
                  gotRunFinished = true;
                  setCurrentStep(undefined);
                  break;

                case 'RUN_ERROR': {
                  gotRunFinished = true;
                  setCurrentStep(undefined);
                  const errText = ev.message ?? ev.error ?? 'An unexpected error occurred. Please try again.';
                  setMessages((prev) => [
                    ...prev,
                    { id: `err-${Date.now()}`, role: 'error' as const, content: errText },
                  ]);
                  console.error('[useAgentStream] RUN_ERROR:', ev);
                  break;
                }
              }
            } catch { /**/ }
          }
        }
      } catch (e: unknown) {
        if ((e as Error).name !== 'AbortError') console.error('[useAgentStream] error:', e);
      } finally {
        setIsRunning(false);
        if (!gotRunFinished) {
          // Stream ended without RUN_FINISHED → graph interrupted
          // Check if waiting for delete confirmation
          const allMsgs = messagesRef.current;
          const lastAiMsg = [...allMsgs]
            .reverse()
            .find((m) => m.role === 'assistant' && m.toolCalls?.length);
          const deleteCall = lastAiMsg?.toolCalls?.find((tc) => tc.name === 'DeleteResources');
          if (deleteCall) {
            setPendingDeleteUrls((deleteCall.args.urls as string[]) ?? []);
          }
        }
      }
    },
    [agentUrl],
  );

  const sendMessage = useCallback(
    (content: string, stateOverride?: Partial<AgentState>) => {
      const userMsg: ChatMessage = { id: `msg-${Date.now()}`, role: 'user', content };
      const updated = [...messagesRef.current, userMsg];
      setMessages(updated);
      runStream(
        updated.map((m) => ({ id: m.id, role: m.role, content: m.content })),
        undefined,
        stateOverride,
      );
    },
    [runStream],
  );

  const confirmDelete = useCallback(
    (confirmed: boolean) => {
      if (pendingDeleteUrls === null) return;
      setPendingDeleteUrls(null);

      const allMsgs = messagesRef.current;
      const lastAiMsg = [...allMsgs]
        .reverse()
        .find((m) => m.role === 'assistant' && m.toolCalls?.some((tc) => tc.name === 'DeleteResources'));
      const deleteCall = lastAiMsg?.toolCalls?.find((tc) => tc.name === 'DeleteResources');

      // Send a tool response message that perform_delete_node will read as messages[-1]
      const toolMsg = {
        id: `tool-${Date.now()}`,
        role: 'tool',
        content: confirmed ? 'YES' : 'NO',
        ...(deleteCall ? { tool_call_id: deleteCall.id } : {}),
      };
      runStream([toolMsg], { resume_value: confirmed ? 'YES' : 'NO' }, undefined);
    },
    [pendingDeleteUrls, runStream],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsRunning(false);
  }, []);

  const updateAgentState = useCallback((updates: Partial<AgentState>) => {
    setAgentState((prev) => ({ ...prev, ...updates }));
  }, []);

  return { agentState, messages, isRunning, currentStep, pendingDeleteUrls, sendMessage, confirmDelete, stop, updateAgentState };
}
