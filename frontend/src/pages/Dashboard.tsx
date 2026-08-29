import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Layout from '../components/Layout'
import type { CheckInResponse, Overview, StudyTask } from '../types'

const empty: Overview = { events: [], exams: [] }
type CheckMode = 'PARTIAL' | 'COMPLETED'

export default function Dashboard() {
  const [data, setData] = useState<Overview>(empty)
  const [loading, setLoading] = useState(true)
  const [planning, setPlanning] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [checkTask, setCheckTask] = useState<StudyTask | null>(null)
  const [checkMode, setCheckMode] = useState<CheckMode>('PARTIAL')
  const [actualEnd, setActualEnd] = useState('')

  const load = async () => { try { setData(await api.overview()); setError('') } catch { setError('백엔드에 연결할 수 없습니다. 8000번 포트의 서버를 실행해 주세요.') } finally { setLoading(false) } }
  useEffect(() => { void load() }, [])
  const planned = useMemo(() => data.exams.flatMap(exam => exam.tasks.map(task => ({ task, exam }))).filter(({ task }) => task.status === 'PLANNED').sort((a, b) => `${a.task.study_date}${a.task.suggested_start_time}`.localeCompare(`${b.task.study_date}${b.task.suggested_start_time}`)), [data])

  const resetDemo = async () => { setPlanning(true); try { setData(await api.resetDemo()); setMessage('시연 데이터가 준비되었습니다. 실제 공부량을 기록해 계획 변화를 확인해 보세요.'); setError('') } catch (reason) { setError((reason as Error).message) } finally { setPlanning(false) } }
  const showResult = (response: CheckInResponse) => setMessage(`${response.replan_explanation} ${response.recommendation} (계획 v${response.previous_version} → v${response.new_version})`)
  const checkIn = async (task: StudyTask, result: 'COMPLETED' | 'PARTIAL' | 'MISSED', scopeEnd?: number) => {
    setPlanning(true)
    try { const response = await api.checkIn(task.id, { result, actual_scope_end: scopeEnd ?? null }); showResult(response); setCheckTask(null); setActualEnd(''); await load() }
    catch (reason) { setError((reason as Error).message) } finally { setPlanning(false) }
  }
  const openCheck = (task: StudyTask, mode: CheckMode) => { setCheckTask(task); setCheckMode(mode); setActualEnd(mode === 'COMPLETED' ? String(task.scope_end) : '') }
  const removeExam = async (id: number, subject: string) => { if (!window.confirm(`${subject} 시험과 연결된 계획을 삭제할까요?`)) return; try { await api.deleteExam(id); setMessage(`${subject} 시험을 삭제했습니다.`); await load() } catch (reason) { setError((reason as Error).message) } }

  return <Layout>
    <section className="hero replan-hero"><div><span className="kicker">KHUNIV · NEXUS CHALLENGE</span><h1>RE:PLAN</h1><p className="hero-tagline">학습 계획을 만들고 디벨롭해주는 나만의 캘린더</p><div className="hero-actions"><button className="btn btn-primary" onClick={resetDemo}>30초 데모</button><Link className="btn btn-secondary" to="/exams/new">시험 등록</Link></div></div></section>
    {error && <div className="notice error">{error}</div>}{message && <div className="notice success insight-notice"><b>RE:PLAN 분석</b><span>{message}</span></div>}
    <section className="section-heading"><div><span className="kicker">ACTIVE EXAMS</span><h2>시험 진행 현황</h2></div><Link to="/exams/new">+ 시험 추가</Link></section>
    {loading ? <div className="empty">불러오는 중...</div> : data.exams.length === 0 ? <div className="empty"><b>아직 등록된 시험이 없습니다.</b><p>데모를 시작하거나 첫 시험을 등록해 보세요.</p></div> : <div className="exam-grid">{data.exams.map(exam => { const percent = Math.min(100, exam.current_passes / exam.target_passes * 100); const behind = exam.forecast_passes + .01 < exam.target_passes; return <article className="exam-card" key={exam.id}><div className="exam-top"><span className="subject-dot"/><div><h3>{exam.subject}</h3><p>{exam.exam_date} {exam.exam_time} · 목표 {exam.target_passes}회독</p></div><button className="icon-delete" aria-label={`${exam.subject} 시험 삭제`} onClick={() => void removeExam(exam.id, exam.subject)}>삭제</button></div><div className="metrics"><div><strong>{exam.current_passes}</strong><span>현재 회독</span></div><div><strong className={behind ? 'warning-text' : ''}>{exam.forecast_passes}</strong><span>현재 속도 예상</span></div><div><strong>{exam.tasks.filter(task => task.status === 'PLANNED').length}</strong><span>남은 블록</span></div></div><div className="progress"><i style={{ width: `${percent}%` }}/></div>{exam.priority_chapters && <p className="priority-note"><b>우선</b> {exam.priority_chapters}</p>}{exam.last_replan_summary && <div className="replan-report"><b>최근 수정</b><p>{exam.last_replan_summary}</p><p className={behind ? 'warning-text' : ''}>{exam.pace_advice}</p></div>} {!exam.last_replan_summary && exam.ai_summary && <p className="ai-summary">{exam.ai_summary}</p>}</article> })}</div>}
    <section className="section-heading"><div><span className="kicker">TODAY & NEXT</span><h2>가장 가까운 공부 계획</h2></div><Link to="/calendar">전체 캘린더</Link></section>
    <div className="task-list">{planned.slice(0, 5).map(({ task, exam }) => <article className="task-row" key={task.id}><div className="date-box"><strong>{new Date(`${task.study_date}T00:00:00`).getDate()}</strong><span>{new Date(`${task.study_date}T00:00:00`).toLocaleDateString('ko-KR', { weekday: 'short' })}</span></div><div className="task-copy"><span>{exam.subject} · {task.pass_number}회독</span><h3>{task.scope_start}–{task.scope_end} {exam.scope_unit}</h3><small>{task.suggested_start_time}–{task.suggested_end_time} · 계획 v{task.plan_version}</small></div><div className="check-actions"><button onClick={() => openCheck(task, 'COMPLETED')}>완료·초과</button><button onClick={() => openCheck(task, 'PARTIAL')}>일부</button><button className="muted" onClick={() => void checkIn(task, 'MISSED')}>미완료</button></div></article>)}{planned.length === 0 && data.exams.length > 0 && <div className="empty">남은 공부 계획이 없습니다.</div>}</div>
    {checkTask && <div className="modal-backdrop"><div className="modal"><span className="kicker">ACTUAL PROGRESS</span><h2>{checkMode === 'COMPLETED' ? '실제로 어디까지 했나요?' : '어디까지 완료했나요?'}</h2><p>예정 범위: {checkTask.scope_start}–{checkTask.scope_end}</p><label>실제 완료 지점<input autoFocus type="number" min={checkTask.scope_start} value={actualEnd} onChange={event => setActualEnd(event.target.value)} placeholder={checkMode === 'COMPLETED' ? '예정보다 더 했다면 큰 숫자 입력' : `${checkTask.scope_end - 1} 이하`}/></label><small className="helper">예정보다 많이 했다면 실제 끝 지점을 입력하세요. 초과분까지 다음 계획에 반영됩니다.</small><div className="modal-actions"><button className="btn btn-secondary" onClick={() => setCheckTask(null)}>취소</button><button className="btn btn-primary" disabled={!actualEnd} onClick={() => void checkIn(checkTask, checkMode, Number(actualEnd))}>기록하고 재계획</button></div></div></div>}
    {planning && <div className="planning-overlay" role="status" aria-live="polite"><div className="planning-card"><i/><b>계획 생성 중</b><p>실제 공부량에 맞춰 남은 계획을 다시 정리하고 있어요.</p></div></div>}
  </Layout>
}
