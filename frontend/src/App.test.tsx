import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import App from './App'
import CalendarPage, { subjectStyle } from './pages/CalendarPage'
import ExamRegister from './pages/ExamRegister'

vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ events: [], exams: [] }) })))

test('renders the RE:PLAN dashboard', async () => {
  render(<App/>)
  expect(screen.getByRole('heading', { name: 'RE:PLAN' })).toBeInTheDocument()
  await waitFor(() => expect(screen.getByText('아직 등록된 시험이 없습니다.')).toBeInTheDocument())
})

test('shows monthly and daily calendars together', async () => {
  await act(async () => { render(<MemoryRouter><CalendarPage/></MemoryRouter>) })
  expect(screen.getByRole('button', { name: '월 + 일' })).toHaveClass('active')
  expect(screen.getByText(/블록 이동/)).toBeInTheDocument()
  const today = new Date().getDate().toString()
  const dayButtons = screen.getAllByRole('button', { name: new RegExp(`^${today}`) })
  fireEvent.click(dayButtons[0])
  expect(screen.getByRole('button', { name: '월 + 일' })).toHaveClass('active')
})

test('switches to the weekly calendar', async () => {
  await act(async () => { render(<MemoryRouter><CalendarPage/></MemoryRouter>) })
  fireEvent.click(screen.getByRole('button', { name: '주간' }))
  expect(screen.getByRole('button', { name: '주간' })).toHaveClass('active')
  expect(screen.getAllByRole('button', { name: /월|화|수|목|금|토|일/ }).length).toBeGreaterThan(1)
})

test('offers weekly recurring dates and a split resize handle', async () => {
  await act(async () => { render(<MemoryRouter><CalendarPage/></MemoryRouter>) })
  fireEvent.click(screen.getByRole('button', { name: '+ 고정 일정' }))
  fireEvent.click(screen.getByRole('checkbox', { name: /매주 반복/ }))
  expect(screen.getByLabelText('반복 종료일')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '월간과 일간 캘린더 너비 조절' })).toBeInTheDocument()
})

test('can hide fixed calendar events', async () => {
  await act(async () => { render(<MemoryRouter><CalendarPage/></MemoryRouter>) })
  const toggle = screen.getByRole('button', { name: '고정 일정 숨기기' })
  expect(toggle).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(toggle)
  expect(screen.getByRole('button', { name: '고정 일정 보이기' })).toHaveAttribute('aria-pressed', 'false')
})

test('assigns different colors to different subject positions', () => {
  expect(subjectStyle(0)).not.toEqual(subjectStyle(1))
})

test('shows planning status only while an exam plan request is running', async () => {
  let finish!: (value: Response) => void
  vi.mocked(fetch).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  render(<MemoryRouter><ExamRegister/></MemoryRouter>)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('과목명'), { target: { value: '생리학' } })
  fireEvent.click(screen.getByRole('button', { name: 'RE:PLAN 만들기' }))
  expect(await screen.findByRole('status')).toHaveTextContent('계획 생성 중')
  finish(new Response('{}', { status: 201, headers: { 'Content-Type': 'application/json' } }))
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
})

test('accepts combined freeform planning preferences for the AI plan', () => {
  render(<MemoryRouter><ExamRegister/></MemoryRouter>)
  const preferences = screen.getByLabelText(/^우선 범위·과목 특성·계획 요구사항/)
  fireEvent.change(preferences, { target: { value: '시험 전 이틀은 복습만 하고 싶어요.' } })
  expect(preferences).toHaveValue('시험 전 이틀은 복습만 하고 싶어요.')
})
