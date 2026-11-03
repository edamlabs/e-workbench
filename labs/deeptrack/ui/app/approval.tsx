"use client";

// The approval stop of the outer graph (`interrupt({"propuesta": …})`), rendered in the chat.
// resolve({decision}) resumes the run; the graph routes "aprobar" to execution, "rechazar" back to the agent.
import { useInterrupt } from "@copilotkit/react-core/v2";

type Stop = { propuesta?: Record<string, unknown> };

function read(value: unknown): Stop {
  if (typeof value === "string") {
    try {
      return JSON.parse(value) as Stop;
    } catch {
      return {};
    }
  }
  return (value ?? {}) as Stop;
}

export function Approval() {
  useInterrupt({
    agentId: "deeptrack",
    render: ({ event, resolve }) => {
      const stop = read(event?.value);
      return (
        <div style={{ border: "1px solid #c33", borderRadius: 8, padding: 12, margin: 8 }}>
          <strong>Aprobación requerida</strong>
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(stop.propuesta ?? stop, null, 2)}</pre>
          <button type="button" onClick={() => resolve({ decision: "aprobar" })}>Aprobar</button>{" "}
          <button type="button" onClick={() => resolve({ decision: "rechazar" })}>Rechazar</button>
        </div>
      );
    },
  });
  return null;
}
