import { Route, BrowserRouter, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Backlog } from './pages/Backlog'
import { DraftStudio } from './pages/DraftStudio'
import { Inbox } from './pages/Inbox'
import { ThisWeek } from './pages/ThisWeek'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Inbox />} />
          <Route path="week" element={<ThisWeek />} />
          <Route path="backlog" element={<Backlog />} />
          <Route path="notes/:id" element={<DraftStudio />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
