"use client";

import Main from "./Main";
import { ModelSelectorProvider } from "@/lib/model-selector-provider";

export default function Page() {
  return (
    <ModelSelectorProvider>
      <div style={{ height: "100vh", overflow: "hidden" }}>
        <Main />
      </div>
    </ModelSelectorProvider>
  );
}
