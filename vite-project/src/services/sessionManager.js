import api from "./api";

const INACTIVITY_TIMEOUT = 15 * 60 * 1000;
const WARNING_TIME = 2 * 60 * 1000;

let inactivityTimer = null;
let warningTimer = null;
let activeListeners = [];

const activityEvents = [
  "mousemove",
  "mousedown",
  "keydown",
  "scroll",
  "touchstart",
  "click",
];

export function startSessionManager({
  onWarning,
  onLogout,
}) {
  stopSessionManager();
  function resetTimers() {
    if (inactivityTimer) {
      clearTimeout(inactivityTimer);
    }

    if (warningTimer) {
      clearTimeout(warningTimer);
    }

    warningTimer = setTimeout(() => {
      if (onWarning) {
        onWarning();
      }
    }, INACTIVITY_TIMEOUT - WARNING_TIME);

    inactivityTimer = setTimeout(() => {
      handleLogout();
    }, INACTIVITY_TIMEOUT);
  }

  async function handleLogout() {
    try {
      await api.post("/logout");
    } catch {
      // Session may already be expired
    }

    stopSessionManager();

    sessionStorage.removeItem("bankAccount");

    if (onLogout) {
      onLogout();
    }
  }

  activeListeners = activityEvents.map((event) => {
    window.addEventListener(event, resetTimers, { passive: true });
    return [event, resetTimers];
  });

  resetTimers();

  return {
    resetTimers,
  };
}

export function stopSessionManager() {
  if (inactivityTimer) {
    clearTimeout(inactivityTimer);
    inactivityTimer = null;
  }

  if (warningTimer) {
    clearTimeout(warningTimer);
    warningTimer = null;
  }

  activeListeners.forEach(([event, listener]) => {
    window.removeEventListener(event, listener);
  });
  activeListeners = [];
}