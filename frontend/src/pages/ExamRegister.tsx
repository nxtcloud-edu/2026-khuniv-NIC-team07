import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import Layout from '../components/Layout'

const futureDate = () => { const value = new Date(); value.setDate(value.getDate() + 14); return value.toISOString().slice(0, 10) }

export default function ExamRegister() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ subject: '', exam_date: futureDate(), exam_time: '09:00', scope_start: 1, scope_end: 200, scope_unit: '페이지', target_passes: 2, planning_preferences: '' })
  const [error, setError] = useState('')
  const [planning, setPlanning] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setPlanning(true); setError(''); try { await api.createExam(form); navigate('/') } catch (reason) { setError((reason as Error).message) } finally { setPlanning(false) } }
  return <Layout>
    <header className="page-header"><span className="kicker">PLAN A NEW EXAM</span><h1>시험과 우선순위를<br/>함께 알려주세요.</h1><p>같은 날 여러 시험도 시간별로 등록할 수 있고, 교수님이 강조한 범위는 AI 계획에서 먼저 고려합니다.</p></header>
    {error && <div className="notice error">{error}</div>}
    <form className="form-card" onSubmit={submit}>
      <div className="form-grid">
        <label className="wide">과목명<input required value={form.subject} onChange={event => setForm({ ...form, subject: event.target.value })} placeholder="예: 생화학"/></label>
        <label>시험일<input required type="date" value={form.exam_date} onChange={event => setForm({ ...form, exam_date: event.target.value })}/></label>
        <label>시험 시간<input required type="time" value={form.exam_time} onChange={event => setForm({ ...form, exam_time: event.target.value })}/></label>
        <label>목표 회독<select value={form.target_passes} onChange={event => setForm({ ...form, target_passes: Number(event.target.value) })}><option value={1}>1회독</option><option value={1.5}>1.5회독</option><option value={2}>2회독</option><option value={3}>3회독</option><option value={4}>4회독</option></select></label>
        <label>단위<select value={form.scope_unit} onChange={event => setForm({ ...form, scope_unit: event.target.value })}><option>페이지</option><option>챕터</option><option>문제</option></select></label>
        <label>범위 시작<input required type="number" min="0" step={form.scope_unit==='챕터'?'0.1':'1'} value={form.scope_start} onChange={event => setForm({ ...form, scope_start: Number(event.target.value) })}/></label>
        <label>범위 끝<input required type="number" min="1" step={form.scope_unit==='챕터'?'0.1':'1'} value={form.scope_end} onChange={event => setForm({ ...form, scope_end: Number(event.target.value) })}/></label>
        <label className="wide">우선 범위·과목 특성·계획 요구사항<textarea value={form.planning_preferences} maxLength={4000} onChange={event => setForm({ ...form, planning_preferences: event.target.value })} placeholder={'예: 3장은 교수님이 특히 강조했어요. 암기 과목이라 짧게 여러 번 보고 싶고, 시험 전 이틀은 복습만 배치해 주세요.'} rows={7}/><small>정해진 형식 없이 자연어로 적어 주세요. 그대로 저장되어 최초 계획과 이후 재계획에 계속 반영됩니다.</small></label>
      </div>
      <div className="form-footer"><p>고정 일정과 다른 시험의 학습 블록을 피해 겹치지 않게 계획합니다.</p><button className="btn btn-primary" disabled={planning}>{planning ? '계획 생성 중…' : 'RE:PLAN 만들기'}</button></div>
    </form>
    {planning && <div className="planning-overlay" role="status" aria-live="polite"><div className="planning-card"><i/><b>계획 생성 중</b><p>시험 범위와 빈 시간을 빠르게 배분하고 있어요.</p></div></div>}
  </Layout>
}
