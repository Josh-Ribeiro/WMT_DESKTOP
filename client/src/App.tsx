import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { lazy, Suspense, type ReactNode } from "react";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import BackendGate from "./components/BackendGate";
import { AuthenticatedLayout } from "./components/AuthenticatedLayout";
import {
  AuthenticationGuard,
  PermissionGuard,
} from "./components/ProtectedRoute";
import OperationalNotifier from "./components/OperationalNotifier";
import UpdateNotifier from "./components/UpdateNotifier";
import { AuthProvider } from "./contexts/AuthContext";
import { LanguageProvider } from "./contexts/LanguageContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { ROUTE_POLICIES, type RouteId } from "./lib/routePolicy";

const Account = lazy(() => import("./pages/Account"));
const ADUsers = lazy(() => import("./pages/ADUsers"));
const AdminSettings = lazy(() => import("./pages/AdminSettings"));
const AdminUsers = lazy(() => import("./pages/AdminUsers"));
const Backup = lazy(() => import("./pages/Backup"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const WorkstationHistory = lazy(() => import("./pages/WorkstationHistory"));
const Login = lazy(() => import("./pages/Login"));
const Monitor = lazy(() => import("./pages/Monitor"));
const NotFound = lazy(() => import("./pages/NotFound"));
const RemoteJobs = lazy(() => import("./pages/RemoteJobs"));
const HostPerformance = lazy(() => import("./pages/HostPerformance"));
const Terms = lazy(() => import("./pages/Terms"));
const MachineReplacement = lazy(() => import("./pages/MachineReplacement"));

function ProtectedPage({
  children,
  route,
}: {
  children: ReactNode;
  route: RouteId;
}) {
  return (
    <PermissionGuard policy={ROUTE_POLICIES[route]}>{children}</PermissionGuard>
  );
}

function ProtectedRouter() {
  return (
    <Switch>
      <Route path="/dashboard">
        <ProtectedPage route="dashboard">
          <Dashboard />
        </ProtectedPage>
      </Route>
      <Route path="/monitor">
        <ProtectedPage route="monitor">
          <Monitor />
        </ProtectedPage>
      </Route>
      <Route path="/ad-users">
        <ProtectedPage route="ad-users">
          <ADUsers />
        </ProtectedPage>
      </Route>
      <Route path="/tasks">
        <ProtectedPage route="tasks">
          <RemoteJobs />
        </ProtectedPage>
      </Route>
      <Route path="/monitor-temps">
        <ProtectedPage route="monitor-temps">
          <HostPerformance />
        </ProtectedPage>
      </Route>
      <Route path="/backup">
        <ProtectedPage route="backup">
          <Backup />
        </ProtectedPage>
      </Route>
      <Route path="/machine-replacement">
        <ProtectedPage route="machine-replacement">
          <MachineReplacement />
        </ProtectedPage>
      </Route>
      <Route path="/history">
        <ProtectedPage route="history">
          <WorkstationHistory />
        </ProtectedPage>
      </Route>
      <Route path="/terms">
        <ProtectedPage route="terms">
          <Terms />
        </ProtectedPage>
      </Route>
      <Route path="/admin/users">
        <ProtectedPage route="admin-users">
          <AdminUsers />
        </ProtectedPage>
      </Route>
      <Route path="/admin/settings">
        <ProtectedPage route="admin-settings">
          <AdminSettings />
        </ProtectedPage>
      </Route>
      <Route path="/account">
        <ProtectedPage route="account">
          <Account />
        </ProtectedPage>
      </Route>
      <Route path="/">
        <ProtectedPage route="dashboard">
          <Dashboard />
        </ProtectedPage>
      </Route>
      <Route path={"/404"} component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route>
        <AuthenticationGuard>
          <AuthenticatedLayout>
            <ProtectedRouter />
          </AuthenticatedLayout>
        </AuthenticationGuard>
      </Route>
    </Switch>
  );
}

function App() {
  return (
    <ThemeProvider defaultTheme="light" switchable>
      <LanguageProvider>
        <ErrorBoundary>
          <BackendGate>
            <AuthProvider>
              <TooltipProvider>
                <Toaster />
                <UpdateNotifier />
                <OperationalNotifier />
                <Suspense
                  fallback={<div className="min-h-screen bg-background" />}
                >
                  <Router />
                </Suspense>
              </TooltipProvider>
            </AuthProvider>
          </BackendGate>
        </ErrorBoundary>
      </LanguageProvider>
    </ThemeProvider>
  );
}

export default App;
