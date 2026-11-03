// The CopilotKit runtime: the browser talks to it, it talks AG-UI to the lab's server (make dev).
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";

const AGENT_URL = process.env.DEEPTRACK_AGENT_URL ?? "http://127.0.0.1:28103/agui";

// One local operator: every thread belongs to "labs", so listing and clearing threads work without auth.
const runtime = new CopilotRuntime({
  agents: { deeptrack: new LangGraphHttpAgent({ url: AGENT_URL }) },
  identifyUser: () => ({ id: "labs", name: "labs" }),
});

const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

export { handler as GET, handler as POST, handler as PATCH, handler as DELETE };
