import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import api, {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../services/api";
import { useToast } from "./useToast";
import ThemeToggle from "./ThemeToggle";

import {
  startSessionManager,
  stopSessionManager,
} from "../services/sessionManager";

export default function Layout() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [sessionWarning, setSessionWarning] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  // Notification state
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notificationLoading, setNotificationLoading] =
    useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const notificationRef = useRef(null);
  const profileRef = useRef(null);
  const sessionManagerRef = useRef(null);

  const account = JSON.parse(
    sessionStorage.getItem("bankAccount") || "{}"
  );

  useEffect(() => {
    sessionManagerRef.current = startSessionManager({
      onWarning: () => {
        setSessionWarning(true);
      },

      onLogout: () => {
        navigate("/", {
          replace: true,
          state: {
            message:
              "You were logged out because your session was inactive.",
          },
        });
      },
    });

    return () => {
      stopSessionManager();
      sessionManagerRef.current = null;
    };
  }, [navigate]);

  // Load notifications when layout opens
  // and refresh every 30 seconds.
  useEffect(() => {
    let active = true;
    function refreshNotifications() {
      getNotifications()
        .then((data) => {
          if (active) {
            setNotifications(data.notifications || []);
            setUnreadCount(data.unread_count || 0);
          }
        })
        .catch((error) => {
          console.error("Failed to load notifications:", error);
        });
    }

    refreshNotifications();

    const interval = setInterval(
      refreshNotifications,
      30000
    );

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Close notification dropdown when clicking outside.
  useEffect(() => {
    function handleOutsideClick(event) {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(event.target)
      ) {
        setNotificationOpen(false);
      }

      if (
        profileRef.current &&
        !profileRef.current.contains(event.target)
      ) {
        setProfileOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setNotificationOpen(false);
        setProfileOpen(false);
        setMobileNavigationOpen(false);
      }
    }

    document.addEventListener(
      "mousedown",
      handleOutsideClick
    );
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener(
        "mousedown",
        handleOutsideClick
      );
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  async function handleNotificationClick(notification) {
    if (notification.read) {
      return;
    }

    try {
      await markNotificationRead(notification.id);

      setNotifications((prev) =>
        prev.map((item) =>
          item.id === notification.id
            ? { ...item, read: true }
            : item
        )
      );

      setUnreadCount((prev) =>
        Math.max(0, prev - 1)
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not update notification.",
        "error"
      );
    }
  }

  async function handleMarkAllRead() {
    if (unreadCount === 0) {
      return;
    }

    setNotificationLoading(true);

    try {
      await markAllNotificationsRead();

      setNotifications((prev) =>
        prev.map((notification) => ({
          ...notification,
          read: true,
        }))
      );

      setUnreadCount(0);

      showToast(
        "All notifications marked as read.",
        "success"
      );
    } catch (error) {
      showToast(
        error.response?.data?.message ||
          "Could not update notifications.",
        "error"
      );
    } finally {
      setNotificationLoading(false);
    }
  }

  async function handleLogout() {
    setMobileNavigationOpen(false);
    setProfileOpen(false);
    setLoggingOut(true);

    try {
      await api.post("/logout");
    } catch {
      // Clear local UI session regardless
    }

    sessionStorage.removeItem("bankAccount");
    navigate("/", { replace: true });
    setLoggingOut(false);
  }

  function formatNotificationTime(createdAt) {
    if (!createdAt) {
      return "";
    }

    const date = new Date(createdAt);
    const now = new Date();

    const seconds = Math.floor(
      (now - date) / 1000
    );

    if (seconds < 60) {
      return "Just now";
    }

    if (seconds < 3600) {
      return `${Math.floor(seconds / 60)}m ago`;
    }

    if (seconds < 86400) {
      return `${Math.floor(seconds / 3600)}h ago`;
    }

    if (seconds < 604800) {
      return `${Math.floor(seconds / 86400)}d ago`;
    }

    return date.toLocaleDateString();
  }

  function getNotificationIcon(type) {
    switch (type) {
      case "SUCCESS":
        return "✓";

      case "WARNING":
        return "!";

      case "ERROR":
        return "×";

      default:
        return "i";
    }
  }

  return (
    <div className="app-shell">
      {mobileNavigationOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobileNavigationOpen(false)}
        />
      )}

      <aside
        className={`sidebar${mobileNavigationOpen ? " sidebar-open" : ""}`}
        id="primary-navigation"
      >
        <div className="sidebar-brand">
          <span className="brand-mark small">B</span>
          <span>BlueBank</span>
        </div>

        <p className="nav-caption">MENU</p>

        <nav
          className="side-nav"
          aria-label="Main navigation"
          onClick={() => setMobileNavigationOpen(false)}
        >
          <NavLink to="/dashboard">
            <span>▦</span> Overview
          </NavLink>

          <NavLink to="/deposit">
            <span>＋</span> Deposit
          </NavLink>

          <NavLink to="/withdraw">
            <span>↗</span> Withdraw
          </NavLink>

          <NavLink to="/transactions">
            <span>↔</span> Transactions
          </NavLink>

          <NavLink to="/scheduled-transfers">
            <span>◷</span> Scheduled transfers
          </NavLink>

          <NavLink to="/insights">
            <span>◌</span> Spending &amp; savings
          </NavLink>

          <NavLink to="/disputes">
            <span>!</span> Disputes
          </NavLink>

          {/* New navigation links */}
          <NavLink to="/beneficiaries">
            <span>♙</span> Beneficiaries
          </NavLink>

          <NavLink to="/transfer">
            <span>⇄</span> Fund Transfer
          </NavLink>

          <NavLink to="/cards">
            <span>▣</span> Cards
          </NavLink>

          <NavLink to="/account">
            <span>♙</span> Account details
          </NavLink>

          <NavLink to="/profile">
            <span>◉</span> Profile & Settings
          </NavLink>

          <NavLink to="/change-pin">
            <span>⌑</span> Change PIN
          </NavLink>

          <NavLink to="/account-statement">
            <span>⎘</span> Account statement
          </NavLink>
        </nav>

        <div className="sidebar-bottom">
          <div className="user-chip">
            <div className="avatar">
              {(account.name || "U")
                .charAt(0)
                .toUpperCase()}
            </div>

            <div className="user-meta">
              <strong>
                {account.name ||
                  "Account holder"}
              </strong>

              <span>Customer</span>
            </div>
          </div>

          <button
            className="logout-button"
            onClick={handleLogout}
            disabled={loggingOut}
          >
            ⇥{" "}
            {loggingOut
              ? "Signing out..."
              : "Log out"}
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-heading">
            <button
              type="button"
              className="mobile-menu-toggle"
              aria-label={
                mobileNavigationOpen
                  ? "Close navigation menu"
                  : "Open navigation menu"
              }
              aria-expanded={mobileNavigationOpen}
              aria-controls="primary-navigation"
              onClick={() =>
                setMobileNavigationOpen((previous) => !previous)
              }
            >
              <span aria-hidden="true">☰</span>
            </button>

            <div className="topbar-copy">
              <span className="topbar-kicker">
                PERSONAL BANKING
              </span>

              <strong>
                Welcome, {account.name || "there"}
              </strong>
            </div>
          </div>

          {/* Existing avatar + notification */}
          <div className="topbar-right">
            <ThemeToggle />

            <div
              className="notification-wrapper"
              ref={notificationRef}
            >
              <button
                type="button"
                className="notification-button"
                aria-label="Notifications"
                aria-expanded={notificationOpen}
                aria-controls="notification-menu"
                onClick={() =>
                  {
                    setProfileOpen(false);
                    setNotificationOpen((prev) => !prev);
                  }
                }
              >
                {/* Realistic bell icon */}
                <svg
                  className="notification-bell"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
                  <path d="M10 21h4" />
                </svg>

                {unreadCount > 0 && (
                  <span className="notification-badge">
                    {unreadCount > 99
                      ? "99+"
                      : unreadCount}
                  </span>
                )}
              </button>

              {notificationOpen && (
                <div
                  className="notification-dropdown"
                  id="notification-menu"
                >
                  <div className="notification-header">
                    <div>
                      <strong>
                        Notifications
                      </strong>

                      <span>
                        {unreadCount > 0
                          ? `${unreadCount} unread`
                          : "You're all caught up"}
                      </span>
                    </div>

                    {unreadCount > 0 && (
                      <button
                        type="button"
                        className="mark-all-read"
                        onClick={
                          handleMarkAllRead
                        }
                        disabled={
                          notificationLoading
                        }
                      >
                        {notificationLoading
                          ? "Updating..."
                          : "Mark all read"}
                      </button>
                    )}
                  </div>

                  <div className="notification-list">
                    {notifications.length ===
                    0 ? (
                      <div className="notification-empty">
                        <div className="notification-empty-icon">
                          ✓
                        </div>

                        <strong>
                          No notifications
                        </strong>

                        <p>
                          Your important banking
                          activity will appear
                          here.
                        </p>
                      </div>
                    ) : (
                      notifications.map(
                        (notification) => (
                          <button
                            type="button"
                            key={
                              notification.id
                            }
                            className={`notification-item ${
                              notification.read
                                ? ""
                                : "unread"
                            }`}
                            onClick={() =>
                              handleNotificationClick(
                                notification
                              )
                            }
                          >
                            <span
                              className={`notification-icon ${
                                (
                                  notification.type ||
                                  "INFO"
                                ).toLowerCase()
                              }`}
                            >
                              {getNotificationIcon(
                                notification.type
                              )}
                            </span>

                            <span className="notification-content">
                              <strong>
                                {
                                  notification.title
                                }
                              </strong>

                              <span>
                                {
                                  notification.message
                                }
                              </span>

                              <small>
                                {formatNotificationTime(
                                  notification.created_at
                                )}
                              </small>
                            </span>

                            {!notification.read && (
                              <span className="notification-unread-dot" />
                            )}
                          </button>
                        )
                      )
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="profile-menu-wrapper" ref={profileRef}>
              <button
                type="button"
                className="topbar-avatar profile-trigger"
                aria-label="Open account menu"
                aria-expanded={profileOpen}
                aria-controls="profile-menu"
                onClick={() => {
                  setNotificationOpen(false);
                  setProfileOpen((previous) => !previous);
                }}
              >
                {(account.name || "U").charAt(0).toUpperCase()}
              </button>

              {profileOpen && (
                <div className="profile-dropdown" id="profile-menu">
                  <div className="profile-dropdown-summary">
                    <span className="profile-dropdown-avatar">
                      {(account.name || "U").charAt(0).toUpperCase()}
                    </span>
                    <div>
                      <strong>{account.name || "Account holder"}</strong>
                      <span>{account.email || "BlueBank customer"}</span>
                    </div>
                  </div>

                  <nav className="profile-dropdown-links" aria-label="Account shortcuts">
                    <NavLink to="/profile" onClick={() => setProfileOpen(false)}>
                      <span aria-hidden="true">◉</span>
                      Profile &amp; settings
                    </NavLink>
                    <NavLink to="/account" onClick={() => setProfileOpen(false)}>
                      <span aria-hidden="true">▤</span>
                      Account details
                    </NavLink>
                    <NavLink to="/change-pin" onClick={() => setProfileOpen(false)}>
                      <span aria-hidden="true">⌑</span>
                      Security &amp; PIN
                    </NavLink>
                  </nav>

                  <button
                    type="button"
                    className="profile-dropdown-logout"
                    onClick={handleLogout}
                    disabled={loggingOut}
                  >
                    <span aria-hidden="true">↪</span>
                    {loggingOut ? "Signing out..." : "Log out"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <section className="page-content">
          <Outlet />
        </section>
      </main>
            {sessionWarning && (
        <div className="session-warning-overlay">
          <div className="session-warning-modal">
            <div className="session-warning-icon">
              !
            </div>

            <h2>Session expiring soon</h2>

            <p>
              You have been inactive for a while.
              You will be logged out soon for your security.
            </p>

            <button
              className="primary-button"
              onClick={() => {
                setSessionWarning(false);
                sessionManagerRef.current?.resetTimers();
              }}
            >
              Continue session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}