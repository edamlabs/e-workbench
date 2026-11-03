"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";
import { Approval } from "./approval";

export default function Page() {
  return (
    <main style={{ height: "100vh" }}>
      <Approval />
      <CopilotChat agentId="deeptrack" />
    </main>
  );
}
