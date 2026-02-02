// ============================================================================
// NotFoundPage.tsx - 404 page
// ============================================================================

import { Link } from '../Router';
import './NotFoundPage.css';

export function NotFoundPage() {
  return (
    <div className="not-found-page">
      <main className="container">
        <div className="not-found-content">
          <div className="error-code">404</div>
          <h1>Page Not Found</h1>
          <p>The page you're looking for doesn't exist or has been moved.</p>
          <div className="actions">
            <Link to="/" className="btn btn-primary">Go Home</Link>
            <Link to="/teams" className="btn btn-secondary">View Teams</Link>
          </div>
        </div>
      </main>
    </div>
  );
}
