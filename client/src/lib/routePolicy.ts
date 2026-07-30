import type { User } from "@/contexts/AuthContext";

export type RouteId =
  | "dashboard"
  | "monitor"
  | "ad-users"
  | "tasks"
  | "monitor-temps"
  | "backup"
  | "machine-replacement"
  | "history"
  | "terms"
  | "admin-users"
  | "admin-settings"
  | "account";

export interface RoutePolicy {
  id: RouteId;
  path: string;
  label: string;
  permission: string;
  roles?: string[];
  navigation: boolean;
}

export const ROUTE_POLICIES: Record<RouteId, RoutePolicy> = {
  dashboard: {
    id: "dashboard",
    path: "/dashboard",
    label: "Dashboard",
    permission: "dashboard",
    navigation: true,
  },
  monitor: {
    id: "monitor",
    path: "/monitor",
    label: "Monitor",
    permission: "monitor",
    navigation: true,
  },
  "ad-users": {
    id: "ad-users",
    path: "/ad-users",
    label: "AD Users",
    permission: "monitor",
    navigation: false,
  },
  tasks: {
    id: "tasks",
    path: "/tasks",
    label: "Tasks",
    permission: "tasks",
    navigation: true,
  },
  "monitor-temps": {
    id: "monitor-temps",
    path: "/monitor-temps",
    label: "Host Performance",
    permission: "monitor",
    navigation: false,
  },
  backup: {
    id: "backup",
    path: "/backup",
    label: "Backup",
    permission: "backup",
    navigation: true,
  },
  "machine-replacement": {
    id: "machine-replacement",
    path: "/machine-replacement",
    label: "Troca de máquina",
    permission: "backup",
    navigation: true,
  },
  history: {
    id: "history",
    path: "/history",
    label: "WK History",
    permission: "history",
    navigation: true,
  },
  terms: {
    id: "terms",
    path: "/terms",
    label: "Terms",
    permission: "terms",
    navigation: true,
  },
  "admin-users": {
    id: "admin-users",
    path: "/admin/users",
    label: "Users",
    permission: "users",
    roles: ["admin"],
    navigation: true,
  },
  "admin-settings": {
    id: "admin-settings",
    path: "/admin/settings",
    label: "Admin Settings",
    permission: "settings",
    roles: ["admin"],
    navigation: false,
  },
  account: {
    id: "account",
    path: "/account",
    label: "Settings",
    permission: "account",
    navigation: true,
  },
};

export const NAVIGATION_ROUTES = Object.values(ROUTE_POLICIES).filter(
  route => route.navigation
);

export function canAccessRoute(
  user: Pick<User, "role" | "permissions">,
  route: RoutePolicy
) {
  if (!user.permissions.includes(route.permission)) return false;
  return !route.roles || route.roles.includes(user.role);
}
