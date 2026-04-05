import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Sets from './pages/Sets';
import CreateSet from './pages/CreateSet';
import SetDetail from './pages/SetDetail';
import Results from './pages/Results';
import SubmissionDetail from './pages/SubmissionDetail';

function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="app-loading">
        <div className="loader-ring">
          <div></div><div></div><div></div><div></div>
        </div>
        <p>Loading EvalAI...</p>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" /> : <Login />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/sets" element={<Sets />} />
        <Route path="/sets/create" element={<CreateSet />} />
        <Route path="/sets/:setId" element={<SetDetail />} />
        <Route path="/results" element={<Results />} />
        <Route path="/results/:id" element={<SubmissionDetail />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? "/dashboard" : "/login"} />} />
    </Routes>
  );
}

export default App;
