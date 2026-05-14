"use client";

import React from "react";
import Split from "react-split";
import { ResearchCanvas } from "@/components/ResearchCanvas";
import { ChatUI } from "@/components/ChatUI";
import { useModelSelectorContext } from "@/lib/model-selector-provider";
import { useAgentStream } from "@/lib/useAgentStream";

const AGENT_URL =
  process.env.NEXT_PUBLIC_AGENT_URL ||
  "/api/agent/research_agent";

const CHAT_SUGGESTIONS = [
  { title: "Vietnam's Economy", message: "Tell me about Vietnam's economy" },
  {
    title: "Amazon vs Walmart",
    message: "Compare the performance of Amazon and Walmart over the last 10 years",
  },
  {
    title: "Commodities Prices",
    message: "How have commodities prices moved since the Global Financial Crisis?",
  },
  {
    title: "Global Military Spending",
    message: "What is the trend of global military spending since the Ukraine war started?",
  },
  {
    title: "Semiconductor Companies",
    message:
      "How has the performance of semiconductor companies (like NVIDIA, AMD, TSMC, Intel) evolved since 2020 in terms of stock prices, revenue, and market share?",
  },
  {
    title: "Rent & Inflation",
    message: "How has the rent, inflation, and average wages trended in top US cities?",
  },
];

export default function Main() {
  const { model } = useModelSelectorContext();
  const [activeSources, setActiveSources] = React.useState<string[]>(["tavily"]);

  const {
    agentState,
    messages,
    isRunning,
    currentStep,
    pendingDeleteUrls,
    sendMessage,
    confirmDelete,
    stop,
    updateAgentState,
  } = useAgentStream({
    agentUrl: AGENT_URL,
    initialState: {
      model,
      research_question: "",
      resources: [],
      report: "",
      search_sources: activeSources,
      logs: [],
    },
  });

  const handleSend = (message: string) => {
    sendMessage(message, { search_sources: activeSources, logs: [] });
  };

  const handleSourcesChange = (newSources: string[]) => {
    setActiveSources(newSources);
    updateAgentState({ search_sources: newSources });
  };

  return (
    <div
      style={{
        height: "100%",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <header className="flex h-14 bg-[#0E103D] text-white items-center px-6 flex-shrink-0 border-b border-white/10">
        <h1 className="font-display text-xl font-semibold tracking-tight">Research Helper</h1>
        {isRunning && currentStep && (
          <div className="ml-4 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            <span className="text-xs text-white/50 font-medium">
              {{
                download: 'Preparing…',
                chat_node: 'Thinking…',
                search_node: 'Searching…',
                critic_node: 'Reviewing…',
              }[currentStep] ?? `${currentStep}…`}
            </span>
          </div>
        )}
      </header>

      <div style={{ flex: 1, minHeight: 0 }}>
        <Split
          sizes={[30, 70]}
          minSize={200}
          gutterSize={10}
          style={{ display: "flex", height: "100%" }}
          gutter={(_, direction) => {
            const gutter = document.createElement("div");
            gutter.className = `gutter gutter-${direction}`;
            const icon = document.createElement("div");
            icon.style.cssText =
              "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;";
            icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>`;
            gutter.appendChild(icon);
            return gutter;
          }}
        >
          {/* Chat panel */}
          <div style={{ height: "100%", overflow: "hidden" }}>
            <ChatUI
              messages={messages}
              isRunning={isRunning}
              hasReport={!!agentState.report}
              pendingDeleteUrls={pendingDeleteUrls}
              onSend={handleSend}
              onStop={stop}
              onConfirmDelete={confirmDelete}
              suggestions={CHAT_SUGGESTIONS}
              activeSources={activeSources}
              onSourcesChange={handleSourcesChange}
              resources={agentState.resources}
            />
          </div>

          {/* Research canvas panel */}
          <div style={{ height: "100%", overflow: "hidden" }}>
            <ResearchCanvas
              agentState={agentState}
              isRunning={isRunning}
              currentStep={currentStep}
              onStateUpdate={updateAgentState}
            />
          </div>
        </Split>
      </div>
    </div>
  );
}
