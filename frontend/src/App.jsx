import { BrowserRouter, Routes, Route } from 'react-router-dom';
import StudentView from './pages/StudentView';
import HostDashboard from './pages/HostDashboard';
import QuizBuilder from './pages/QuizBuilder';
import AnalyticsDashboard from './pages/AnalyticsDashboard';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <Routes>
          {/* Default route is the student join screen */}
          <Route path="/" element={<StudentView />} />
          <Route path="/host" element={<HostDashboard />} />
          <Route path="/create" element={<QuizBuilder />} />
          <Route path="/create/:quizId" element={<QuizBuilder />} />
          <Route path="/analytics" element={<AnalyticsDashboard />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;