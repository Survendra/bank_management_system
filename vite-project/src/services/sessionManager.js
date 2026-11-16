import api from "./api";

const INACTIVITY_TIMEOUT = 15 * 60 * 1000;
const WARNING_TIME = 2 * 60 * 1000;

let inactivityTimer = null;
let warningTimer = null;

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
  let warningShown = false;

  function resetTimers() {
    warningShown = false;

    if (inactivityTimer) {
      clearTimeout(inactivityTimer);
    }

    if (warningTimer) {
      clearTimeout(warningTimer);
    }

    warningTimer = setTimeout(() => {
      warningShown = true;

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

  activityEvents.forEach((event) => {
    window.addEventListener(event, resetTimers, {
      passive: true,
    });
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
}