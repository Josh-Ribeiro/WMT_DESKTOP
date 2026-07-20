import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { lazy, Suspense } from "react";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import OperationalNotifier from "./components/OperationalNotifier";
import UpdateNotifier from "./components/UpdateNotifier";
import { LanguageProvider } from "./contexts/LanguageContext";
import { ThemeProvider } from "./contexts/ThemeContext";

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


function Router() {
  return (
    <Switch>
      <Route path={"/login"} component={Login} />
      <Route path={"/dashboard"} component={Dashboard} />
      <Route path={"/monitor"} component={Monitor} />
      <Route path={"/ad-users"} component={ADUsers} />
      <Route path={"/tasks"} component={RemoteJobs} />
      <Route path={"/monitor-temps"} component={HostPerformance} />
      <Route path={"/backup"} component={Backup} />

      <Route path={"/history"} component={WorkstationHistory} />
      <Route path={"/terms"} component={Terms} />
      <Route path={"/admin/users"} component={AdminUsers} />
      <Route path={"/admin/settings"} component={AdminSettings} />
      <Route path={"/account"} component={Account} />
      <Route path={"/"} component={Dashboard} />
      <Route path={"/404"} component={NotFound} />
      {/* Final fallback route */}
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider
        defaultTheme="light"
        switchable
      >
        <LanguageProvider>
          <TooltipProvider>
            <Toaster />
            <UpdateNotifier />
            <OperationalNotifier />
            <Suspense fallback={<div className="min-h-screen bg-background" />}>
              <Router />
            </Suspense>
          </TooltipProvider>
        </LanguageProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
