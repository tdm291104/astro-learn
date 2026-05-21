// Mirrors backend/schemas/agent_schema.py + backend/agents/base/agent_message.py.
export type AgentStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AgentInfo = {
  name: string;
  description: string;
  capabilities: string[];
  // null means the agent accepts any dict.
  input_schema: Record<string, unknown> | null;
};

export type AgentRunRequest = {
  agent_name: string;
  task_input: Record<string, unknown>;
  session_id?: string | null;
  stream?: boolean; // default false
};

export type AgentResponse = {
  id: string;
  user_id: string;
  session_id: string | null;
  agent_name: string;
  status: AgentStatus;
  task_input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  // Mirrored from AgentState for progress between status polls.
  step_count: number;
  current_step: string | null;
  progress: number | null; // 0.0 – 1.0, NULL for open-ended runs
  started_at: string | null; // ISO datetime
  finished_at: string | null;
  created_at: string;
};

export type AgentStatusResponse = {
  id: string;
  status: AgentStatus;
  progress: number | null; // 0.0 – 1.0
  current_step: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type AgentMessageRole = "system" | "user" | "assistant" | "tool";

export type ToolCall = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
};

export type AgentMessage = {
  id: string;
  role: AgentMessageRole;
  content: string;
  name: string | null;
  tool_calls: ToolCall[] | null;
  tool_call_id: string | null;
  extra: Record<string, unknown>;
  created_at: string;
};
