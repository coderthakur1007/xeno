"use client";

import { useState, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Zap, LayoutDashboard, Users, Flag, BarChart3,
  UserCircle, Shield, Sun, Moon, LogOut, Menu, X,
} from "lucide-react";
import { useTheme } from "./ThemeProvider";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/audiences", label: "Audiences", icon: Users },
  { href: "/campaigns", label: "Campaigns", icon: Flag },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/customers", label: "Customers", icon: UserCircle },
  { href: "/admin", label: "Admin", icon: Shield },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userEmail, setUserEmail] = useState<string>("");

  useEffect(() => {
    const email = localStorage.getItem("xeno_email") || "";
    setUserEmail(email);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("xeno_token");
    localStorage.removeItem("xeno_email");
    localStorage.removeItem("xeno_user");
    router.push("/login");
  };

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const initials = userEmail
    ? userEmail.substring(0, 2).toUpperCase()
    : "XA";

  return (
    <>
      <button
        className="mobile-menu-btn"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X /> : <Menu />}
      </button>

      {mobileOpen && (
        <div
          className={`sidebar-overlay${mobileOpen ? " open" : ""}`}
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside className={`sidebar${mobileOpen ? " open" : ""}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <Zap />
          </div>
          <span className="sidebar-brand-text">Xeno</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`sidebar-nav-item${isActive(item.href) ? " active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                setMobileOpen(false);
                router.push(item.href);
              }}
            >
              <item.icon />
              {item.label}
            </a>
          ))}
        </nav>

        <div className="sidebar-footer">
          {userEmail && (
            <div className="sidebar-user">
              <div className="sidebar-avatar">{initials}</div>
              <div className="sidebar-user-info">
                <div className="sidebar-user-name">User</div>
                <div className="sidebar-user-email">{userEmail}</div>
              </div>
            </div>
          )}

          <button className="sidebar-toggle-theme" onClick={toggleTheme}>
            {theme === "dark" ? <Sun /> : <Moon />}
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>

          <button className="sidebar-logout" onClick={handleLogout}>
            <LogOut />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
