import { request } from './client'

export type PathNode = {
  id: string
  name: string
  parent_id: string | null
  kind?: string
  code?: string
  gap?: boolean
  gap_reason?: string
  children?: PathNode[]
  path?: { id: string; name: string }[]
  path_text?: string
  parent_name?: string
  [key: string]: unknown
}

export type PathReview = {
  id: number
  code: string
  client_ref: string
  node_id: string
  node_name: string
  submitted_parent_id: string | null
  submitted_parent_name: string
  submitted_path: { id: string; name: string }[]
  submitted_path_text: string
  scope_label?: string
  note: string
  draft_note?: string
  status: string
  assignee?: string
  conform_entry_id?: number
  conform_code?: string
  current_path?: { id: string; name: string }[]
  current_path_text?: string
  path_changed?: boolean
  conflict?: boolean
  original_scope_intact?: boolean
  can_complete_original?: boolean
  must_relink?: boolean
  guidance?: string
  return_route?: string
  workbench_route?: string
  resolution_mode?: string
  relinked?: boolean
  relinked_path_text?: string
  completion_note?: string
  created_at?: string
  claimed_at?: string
  completed_at?: string
  [key: string]: unknown
}

type ApiEnvelope<T> = { ok?: boolean; message?: string; entry?: T; items?: T[]; total?: number }

async function parse<T>(response: Response): Promise<T> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail
    const message = typeof detail === 'string'
      ? detail
      : (detail as { message?: string } | null)?.message
        ?? `接口返回 ${response.status}，请重试`
    const error = new Error(message) as Error & { payload?: unknown }
    error.payload = payload
    throw error
  }
  return payload as T
}

export async function getTree(): Promise<{ items: PathNode[]; nodes: PathNode[] }> {
  return parse(await request('/api/path-locator/tree'))
}

export async function getCandidates(params: {
  name?: string
  parent_id?: string
  gap_only?: boolean
}): Promise<{ items: PathNode[]; total: number }> {
  const query = new URLSearchParams()
  if (params.name) query.set('name', params.name)
  if (params.parent_id) query.set('parent_id', params.parent_id)
  if (params.gap_only) query.set('gap_only', 'true')
  return parse(await request(`/api/path-locator/candidates?${query.toString()}`))
}

export async function moveNode(
  nodeId: string,
  newParentId = 'relocated-parent',
): Promise<ApiEnvelope<{ old_path?: string; new_path?: string }>> {
  return parse(await request(`/api/path-locator/nodes/${encodeURIComponent(nodeId)}/move`, {
    method: 'POST',
    body: JSON.stringify({ new_parent_id: newParentId }),
  }))
}

export async function listReviews(): Promise<{ items: PathReview[]; total: number }> {
  return parse(await request('/api/path-reviews'))
}

export async function getReview(id: string | number): Promise<ApiEnvelope<PathReview>> {
  return parse(await request(`/api/path-reviews/${encodeURIComponent(String(id))}`))
}

export async function createReview(values: {
  node_id: string
  note: string
  client_ref: string
}): Promise<ApiEnvelope<PathReview>> {
  return parse(await request('/api/path-reviews', {
    method: 'POST',
    body: JSON.stringify(values),
  }))
}

export async function saveReviewDraft(
  id: number | string,
  note: string,
): Promise<ApiEnvelope<PathReview>> {
  return parse(await request(`/api/path-reviews/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ note }),
  }))
}

export async function claimReview(id: number | string): Promise<ApiEnvelope<PathReview>> {
  return parse(await request(`/api/path-reviews/${id}/claim`, {
    method: 'POST',
    body: JSON.stringify({ assignee: '复核人' }),
  }))
}

export async function relinkReview(id: number | string): Promise<ApiEnvelope<PathReview>> {
  return parse(await request(`/api/path-reviews/${id}/relink`, { method: 'POST' }))
}

export async function completeReview(
  id: number | string,
  values: { mode: 'original' | 'relink'; completion_note?: string; result?: string },
): Promise<ApiEnvelope<PathReview>> {
  return parse(await request(`/api/path-reviews/${id}/complete`, {
    method: 'POST',
    body: JSON.stringify(values),
  }))
}
