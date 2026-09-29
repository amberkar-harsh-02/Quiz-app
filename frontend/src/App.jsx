import { BrowserRouter, Routes, Route } from 'react-router-dom';
import StudentView from './pages/StudentView';
import HostDashboard from './pages/HostDashboard';
import QuizBuilder from './pages/QuizBuilder';
import AnalyticsDashboard from './pages/AnalyticsDashboard';

// "/quiz-app" rather than "/quiz-app/", so the address works with or without the trailing slash
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

function App() {
  return (
    <BrowserRouter basename={basename}>
      <div className="min-h-screen">
        <Routes>
          {/* Default route is the student join screen, which is also the sign-in page */}
          <Route path="/" element={<StudentView />} />
          <Route path="/login" element={<StudentView />} />
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