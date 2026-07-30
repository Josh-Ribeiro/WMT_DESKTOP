import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { UserFormDialog } from "@/components/UserFormDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useAuthenticatedUser } from "@/hooks/useAuth";
import { useApi } from "@/hooks/useApi";
import { useLocation } from "wouter";
import {
  Plus,
  Edit2,
  Trash2,
  Lock,
  Unlock,
  Search,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { apiRequest } from "@/lib/api";

interface User {
  id: string;
  username: string;
  display_name?: string;
  email: string;
  role: "admin" | "operator" | "viewer";
  role_source?: "manual" | "sso" | string;
  status: "active" | "inactive" | "locked";
  last_login: string;
  created_at: string;
  auth_source?: "windows" | "local" | string;
  domain?: string;
  upn?: string;
}

interface UsersData {
  users: User[];
  total: number;
}

export default function AdminUsers() {
  const user = useAuthenticatedUser();
  const [, navigate] = useLocation();
  const [searchTerm, setSearchTerm] = useState("");
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [isUserFormOpen, setIsUserFormOpen] = useState(false);
  const [deletingUser, setDeletingUser] = useState<User | null>(null);
  const { data, loading, error, refetch } = useApi<UsersData>("/api/users");
  const users = data?.users || [];

  const handleAddUser = () => {
    setEditingUser(null);
    setIsUserFormOpen(true);
  };

  const handleSubmitUser = (payload: Partial<User> & { password?: string }) => {
    const request = editingUser
      ? apiRequest(`/api/users/${editingUser.id}`, {
          method: "PUT",
          body: JSON.stringify({
            email: payload.email,
            role: payload.role,
            status: payload.status,
          }),
        })
      : apiRequest("/api/users", {
          method: "POST",
          body: JSON.stringify(payload),
        });

    toast.promise(
      request.then(() => refetch()),
      {
        loading: editingUser ? "Updating user..." : "Creating new user...",
        success: editingUser
          ? "User updated successfully"
          : "User created successfully",
        error: err =>
          err instanceof Error ? err.message : "Failed to save user",
      }
    );
  };

  const handleEditUser = (target: User) => {
    setEditingUser(target);
    setIsUserFormOpen(true);
  };

  const handleDeleteUser = (userId: string) => {
    toast.promise(
      apiRequest(`/api/users/${userId}`, { method: "DELETE" }).then(() =>
        refetch()
      ),
      {
        loading: "Deleting user...",
        success: "User deleted successfully",
        error: "Failed to delete user",
      }
    );
  };

  const handleLockUser = (userId: string) => {
    toast.promise(
      apiRequest(`/api/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "locked" }),
      }).then(() => refetch()),
      {
        loading: "Locking user...",
        success: "User locked",
        error: "Failed to lock user",
      }
    );
  };

  const handleUnlockUser = (userId: string) => {
    toast.promise(
      apiRequest(`/api/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "active" }),
      }).then(() => refetch()),
      {
        loading: "Unlocking user...",
        success: "User unlocked",
        error: "Failed to unlock user",
      }
    );
  };

  const filteredUsers = users.filter(
    u =>
      u.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (u.display_name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      (u.upn || "").toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case "admin":
        return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
      case "operator":
        return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
      case "viewer":
        return "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "text-green-600 dark:text-green-400";
      case "inactive":
        return "text-gray-600 dark:text-gray-400";
      case "locked":
        return "text-red-600 dark:text-red-400";
      default:
        return "text-gray-600";
    }
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden bg-background">
      <main className="h-full min-w-0 flex-1 overflow-auto">
        <div className="p-8">
          {/* Header */}
          <div className="wmt-header mb-8 flex min-w-0 flex-col gap-4 rounded-xl border p-5 text-slate-100 shadow-lg sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h1 className="text-3xl font-bold text-white">User Management</h1>
              <p className="mt-1 text-slate-400">
                Manage system users and permissions
              </p>
            </div>
            <Button onClick={handleAddUser} className="gap-2">
              <Plus size={18} />
              Add User
            </Button>
          </div>

          {/* Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total Users
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{users.length}</div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Active Users
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {users.filter(u => u.status === "active").length}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Administrators
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">
                  {users.filter(u => u.role === "admin").length}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Search */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg">Search Users</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative">
                <Search
                  className="absolute left-3 top-2.5 text-muted-foreground"
                  size={18}
                />
                <Input
                  placeholder="Search by username or email..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </CardContent>
          </Card>

          {/* Users Table */}
          <Card>
            <CardHeader>
              <CardTitle>Users ({filteredUsers.length})</CardTitle>
              <CardDescription>Manage all system users</CardDescription>
            </CardHeader>
            <CardContent>
              {loading && !data ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2
                    className="animate-spin text-muted-foreground"
                    size={32}
                  />
                </div>
              ) : error ? (
                <p className="text-sm text-red-700 dark:text-red-300">
                  {error}
                </p>
              ) : filteredUsers.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Username
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Email
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Source
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Role
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Status
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Last Login
                        </th>
                        <th className="text-left py-3 px-4 font-semibold text-foreground">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers.map(u => (
                        <tr
                          key={u.id}
                          className="border-b border-border hover:bg-muted/50 transition-colors"
                        >
                          <td className="py-3 px-4 text-foreground font-medium">
                            <div className="min-w-0">
                              <p>{u.display_name || u.username}</p>
                              <p className="text-xs font-normal text-muted-foreground">
                                {u.domain
                                  ? `${u.domain}\\${u.username}`
                                  : u.username}
                              </p>
                            </div>
                          </td>
                          <td className="py-3 px-4 text-muted-foreground">
                            {u.email}
                          </td>
                          <td className="py-3 px-4">
                            <span className="rounded bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
                              {(u.auth_source || "local").toUpperCase()}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-1 rounded text-xs font-medium ${getRoleBadgeColor(
                                u.role
                              )}`}
                            >
                              {u.role.toUpperCase()}
                            </span>
                            {u.role_source && (
                              <p className="mt-1 text-[11px] text-muted-foreground">
                                {u.role_source === "manual" ? "Manual" : "SSO"}
                              </p>
                            )}
                          </td>
                          <td
                            className={`py-3 px-4 font-medium ${getStatusColor(u.status)}`}
                          >
                            {u.status.toUpperCase()}
                          </td>
                          <td className="py-3 px-4 text-muted-foreground text-xs">
                            {u.last_login}
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleEditUser(u)}
                                title="Edit"
                              >
                                <Edit2 size={14} />
                              </Button>
                              {u.status === "locked" ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleUnlockUser(u.id)}
                                  title="Unlock"
                                >
                                  <Unlock size={14} />
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleLockUser(u.id)}
                                  title="Lock"
                                >
                                  <Lock size={14} />
                                </Button>
                              )}
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={() => setDeletingUser(u)}
                                title="Delete"
                              >
                                <Trash2 size={14} />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No users found
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
      <UserFormDialog
        open={isUserFormOpen}
        title={editingUser ? "Edit User" : "Add User"}
        initialData={editingUser || undefined}
        onClose={() => setIsUserFormOpen(false)}
        onSubmit={handleSubmitUser}
      />
      <ConfirmDialog
        open={!!deletingUser}
        title="Delete user"
        description={`Delete ${deletingUser?.username || "this user"}? This cannot be undone.`}
        actionLabel="Delete"
        isDestructive
        onCancel={() => setDeletingUser(null)}
        onConfirm={() => {
          if (deletingUser) {
            handleDeleteUser(deletingUser.id);
          }
          setDeletingUser(null);
        }}
      />
    </div>
  );
}
