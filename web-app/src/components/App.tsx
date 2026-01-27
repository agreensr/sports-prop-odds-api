// ============================================================================
// App.tsx - Main React app wrapper (client-side only)
// ============================================================================

import { Suspense, useEffect, useState } from 'react';
import { Router } from './Router';

export default function App() {
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  if (!isMounted) {
    return <div className="app-loading">Loading...</div>;
  }

  return (
    <Suspense fallback={<div className="app-loading">Loading...</div>}>
      <Router />
    </Suspense>
  );
}
