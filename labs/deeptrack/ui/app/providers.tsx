"use client";

import { CopilotKitProvider } from "@copilotkit/react-core/v2";

export function Providers({ children }: { children: React.ReactNode }) {
  return <CopilotKitProvider runtimeUrl="/api/copilotkit">{children}</CopilotKitProvider>;
}
