import { describe, expect, it } from "vitest";
import {
  NAVIGATION_ROUTES,
  ROUTE_POLICIES,
  canAccessRoute,
} from "./routePolicy";

const viewer = {
  role: "viewer",
  permissions: ["dashboard", "monitor", "tasks", "account"],
};
const operator = {
  role: "operator",
  permissions: [
    "dashboard",
    "monitor",
    "tasks",
    "backup",
    "history",
    "terms",
    "account",
  ],
};
const admin = {
  role: "admin",
  permissions: [
    "dashboard",
    "monitor",
    "tasks",
    "backup",
    "history",
    "terms",
    "users",
    "settings",
    "account",
  ],
};

describe("route policy", () => {
  it("keeps administrative routes exclusive to administrators", () => {
    expect(canAccessRoute(operator, ROUTE_POLICIES["admin-users"])).toBe(false);
    expect(canAccessRoute(admin, ROUTE_POLICIES["admin-users"])).toBe(true);
    expect(canAccessRoute(admin, ROUTE_POLICIES["admin-settings"])).toBe(true);
  });

  it("does not grant routes from role alone without the permission", () => {
    expect(
      canAccessRoute(
        { role: "admin", permissions: ["dashboard"] },
        ROUTE_POLICIES["admin-settings"]
      )
    ).toBe(false);
  });

  it("uses the dedicated history permission", () => {
    expect(canAccessRoute(viewer, ROUTE_POLICIES.history)).toBe(false);
    expect(canAccessRoute(operator, ROUTE_POLICIES.history)).toBe(true);
  });

  it("maps secondary tools to their parent capability", () => {
    expect(canAccessRoute(viewer, ROUTE_POLICIES["ad-users"])).toBe(true);
    expect(canAccessRoute(viewer, ROUTE_POLICIES["monitor-temps"])).toBe(true);
    expect(canAccessRoute(viewer, ROUTE_POLICIES["machine-replacement"])).toBe(
      false
    );
    expect(
      canAccessRoute(operator, ROUTE_POLICIES["machine-replacement"])
    ).toBe(true);
  });

  it("only exposes routes marked for navigation in the sidebar", () => {
    expect(NAVIGATION_ROUTES.every(route => route.navigation)).toBe(true);
    expect(NAVIGATION_ROUTES).not.toContain(ROUTE_POLICIES["ad-users"]);
    expect(NAVIGATION_ROUTES).not.toContain(ROUTE_POLICIES["monitor-temps"]);
    expect(NAVIGATION_ROUTES).not.toContain(ROUTE_POLICIES["admin-settings"]);
  });
});
