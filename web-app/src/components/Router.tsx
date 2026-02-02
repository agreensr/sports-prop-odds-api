// ============================================================================
// Router.tsx - Client-side hash-based router
// ============================================================================

import { useEffect, useState } from 'react';
import { HomePage } from './pages/HomePage';
import { TeamsPage } from './pages/TeamsPage';
import { TeamDetailPage } from './pages/TeamDetailPage';
import { PredictionsPage } from './pages/PredictionsPage';
import { InjuriesPage } from './pages/InjuriesPage';
import { ParlaysPage } from './pages/ParlaysPage';
import { GamePage } from './pages/GamePage';
import { NotFoundPage } from './pages/NotFoundPage';

type RouteComponent = React.ComponentType<{ params: Record<string, string> }>;

interface Route {
  pattern: RegExp;
  component: RouteComponent;
}

const routes: Route[] = [
  { pattern: /^\/?$/, component: HomePage as RouteComponent },
  { pattern: /^\/teams\/?$/, component: TeamsPage as RouteComponent },
  { pattern: /^\/team\/([^\/]+)\/?$/, component: TeamDetailPage as RouteComponent },
  { pattern: /^\/predictions\/?$/, component: PredictionsPage as RouteComponent },
  { pattern: /^\/injuries\/?$/, component: InjuriesPage as RouteComponent },
  { pattern: /^\/parlays\/?$/, component: ParlaysPage as RouteComponent },
  { pattern: /^\/game\/([^\/]+)\/?$/, component: GamePage as RouteComponent },
];

export function Router() {
  const [currentPath, setCurrentPath] = useState(() => {
    // Get initial path from hash (only on client)
    if (typeof window !== 'undefined') {
      return window.location.hash.slice(1) || '/';
    }
    return '/';
  });

  const [routeParams, setRouteParams] = useState<Record<string, string>>({});

  useEffect(() => {
    // Only run on client
    if (typeof window === 'undefined') {
      return;
    }

    const handleHashChange = () => {
      const hash = window.location.hash.slice(1) || '/';
      setCurrentPath(hash);
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // Find matching route
  let matchedRoute: (Route & { params: Record<string, string> }) | null = null;

  for (const route of routes) {
    const match = currentPath.match(route.pattern);
    if (match) {
      const params: Record<string, string> = {};
      // Extract named groups from regex
      if (match.length > 1) {
        match.slice(1).forEach((value, index) => {
          params[`param${index}`] = value;
        });
      }
      matchedRoute = { ...route, params };
      break;
    }
  }

  const Component = matchedRoute?.component || NotFoundPage;

  return (
    <div className="router">
      <Component params={matchedRoute?.params || {}} />
    </div>
  );
}

// ============================================================================
// Navigation Helper
// ============================================================================

export function navigate(path: string) {
  window.location.hash = path;
}

export function useNavigate() {
  return navigate;
}

// ============================================================================
// Link Component
// ============================================================================

interface LinkProps {
  to: string;
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Link({ to, children, className = '', onClick }: LinkProps) {
  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    onClick?.();
    navigate(to);
  };

  return (
    <a
      href={`#${to}`}
      className={className}
      onClick={handleClick}
    >
      {children}
    </a>
  );
}
