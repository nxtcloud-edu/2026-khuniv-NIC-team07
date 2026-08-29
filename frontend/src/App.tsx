import { BrowserRouter, Route, Routes } from 'react-router-dom'
import CalendarPage from './pages/CalendarPage'
import Dashboard from './pages/Dashboard'
import ExamRegister from './pages/ExamRegister'

export default function App() { return <BrowserRouter><Routes><Route path="/" element={<Dashboard/>}/><Route path="/calendar" element={<CalendarPage/>}/><Route path="/exams/new" element={<ExamRegister/>}/></Routes></BrowserRouter> }
