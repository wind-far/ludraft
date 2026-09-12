import client from './client'
import type { ApiResponse, TeamStatus } from './types'

export async function fetchTeamStatus(): Promise<TeamStatus> {
  const { data } = await client.get<ApiResponse<TeamStatus>>('/codebuddy/team')
  return data.data
}
