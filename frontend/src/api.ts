import type { CheckInResponse, Overview } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json', ...options?.headers }, ...options })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '요청에 실패했습니다.' }))
    throw new Error(typeof error.detail === 'string' ? error.detail : '입력값을 확인해 주세요.')
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  overview: () => request<Overview>('/api/overview'),
  resetDemo: () => request<Overview>('/api/demo/reset', { method: 'POST' }),
  createEvent: (payload: object) => request('/api/events', { method: 'POST', body: JSON.stringify(payload) }),
  createRecurringEvent: (payload: object) => request('/api/events/recurring', { method: 'POST', body: JSON.stringify(payload) }),
  updateEventTime: (eventId: number, payload: object) => request(`/api/events/${eventId}/time`, { method: 'PATCH', body: JSON.stringify(payload) }),
  createExam: (payload: object) => request('/api/exams', { method: 'POST', body: JSON.stringify(payload) }),
  deleteExam: (examId: number) => request<void>(`/api/exams/${examId}`, { method: 'DELETE' }),
  updateTaskTime: (taskId: number, payload: object) => request(`/api/tasks/${taskId}/time`, { method: 'PATCH', body: JSON.stringify(payload) }),
  checkIn: (taskId: number, payload: object) => request<CheckInResponse>(`/api/tasks/${taskId}/check-in`, { method: 'POST', body: JSON.stringify(payload) }),
}
