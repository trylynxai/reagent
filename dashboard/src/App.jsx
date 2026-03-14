import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Overview from './pages/Overview.jsx';
import Runs from './pages/Runs.jsx';
import RunView from './pages/RunView.jsx';
import Failures from './pages/Failures.jsx';
import Search from './pages/Search.jsx';
import TraceInspect from './pages/TraceInspect.jsx';
import ReplayPlayer from './pages/ReplayPlayer.jsx';
import RunRedirect from './pages/RunRedirect.jsx';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:runId" element={<RunRedirect />} />
        <Route path="trace/:runId" element={<TraceInspect />} />
        <Route path="replay/:runId" element={<ReplayPlayer />} />
        <Route path="failures" element={<Failures />} />
        <Route path="search" element={<Search />} />
      </Route>
    </Routes>
  );
}
