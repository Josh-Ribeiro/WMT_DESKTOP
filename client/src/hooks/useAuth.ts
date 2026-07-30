import { useAuth } from "@/contexts/AuthContext";

export { useAuth };
export type { AuthContextValue, User } from "@/contexts/AuthContext";

export function useAuthenticatedUser() {
  const { user } = useAuth();
  if (!user) {
    throw new Error("useAuthenticatedUser requires AuthenticationGuard");
  }
  return user;
}
