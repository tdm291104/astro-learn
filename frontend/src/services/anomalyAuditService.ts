// Delegates audit runs to the reflexion_data_analyst agent.

import { API_ENDPOINTS } from "@/lib/constants";
import { agentService } from "@/services/agentService";
import { api } from "@/services/api";
import type { AgentResponse } from "@/types/agent.types";
import type { SampleFitsListResponse } from "@/types/astronomy.types";

export const anomalyAuditService = {
  async listSamples(): Promise<SampleFitsListResponse> {
    const res = await api.get<SampleFitsListResponse>(API_ENDPOINTS.sampleFits);
    return res.data;
  },

  async runAudit(
    fileId: string,
    taskDescription?: string,
  ): Promise<AgentResponse> {
    return agentService.run({
      agent_name: "reflexion_data_analyst",
      task_input: {
        file_id: fileId,
        ...(taskDescription ? { task_description: taskDescription } : {}),
      },
      stream: false,
    });
  },
};
