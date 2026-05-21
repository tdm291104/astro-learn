import { API_ENDPOINTS } from "@/lib/constants";
import { api } from "@/services/api";
import type {
  AgentInfo,
  AgentResponse,
  AgentRunRequest,
  AgentStatusResponse,
} from "@/types/agent.types";

export const agentService = {
  async list(): Promise<AgentInfo[]> {
    const res = await api.get<AgentInfo[]>(API_ENDPOINTS.agents);
    return res.data;
  },

  // Force stream:false; SSE variant lives in useAgentStream.
  async run(body: AgentRunRequest): Promise<AgentResponse> {
    const res = await api.post<AgentResponse>(API_ENDPOINTS.runAgent, {
      ...body,
      stream: false,
    });
    return res.data;
  },

  async get(runId: string): Promise<AgentResponse> {
    const res = await api.get<AgentResponse>(API_ENDPOINTS.agentRun(runId));
    return res.data;
  },

  async status(runId: string): Promise<AgentStatusResponse> {
    const res = await api.get<AgentStatusResponse>(
      API_ENDPOINTS.agentStatus(runId),
    );
    return res.data;
  },
};
