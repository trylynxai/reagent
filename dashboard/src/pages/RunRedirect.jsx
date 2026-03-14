import { Navigate, useParams } from 'react-router-dom';

export default function RunRedirect() {
  const { runId } = useParams();
  return <Navigate to={`/trace/${runId}`} replace />;
}
