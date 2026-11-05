"use client";

import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";
import { Approval } from "./approval";

// The chat, and a door to etrack's live canvas on the same thread. The lab's server mounts the canvas at /etrack; the
// link goes there directly — a dev proxy holds Server-Sent Events back, so the canvas is never proxied.
const VIEWER = process.env.NEXT_PUBLIC_DEEPTRACK_VIEWER_URL ?? "http://127.0.0.1:28103/etrack";

function Live() {
  const { agent } = useAgent({ agentId: "deeptrack" });
  const href = `${VIEWER}/?thread=${encodeURIComponent(agent.threadId ?? "")}`;
  return (
    // the thread id is minted in the browser: the server's render cannot know it, so the link is the client's alone.
    <a href={href} target="_blank" rel="noreferrer" suppressHydrationWarning style={{ position: "fixed", top: 12, right: 16, zIndex: 10 }}>
      Ver en vivo ↗
    </a>
  );
}

export default function Page() {
  return (
    <main style={{ height: "100vh" }}>
      <Live />
      <Approval />
      <CopilotChat agentId="deeptrack" />
    </main>
  );
}
