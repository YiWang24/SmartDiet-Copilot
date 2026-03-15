const DEFAULT_DURATION = 3800;

export function createToast({ type = "info", message, duration = DEFAULT_DURATION }) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    message,
    duration,
    visible: true,
  };
}

export function toastReducer(state, action) {
  switch (action.type) {
    case "add":
      return [...state, action.toast];
    case "dismiss":
      return state.map((toast) =>
        toast.id === action.id ? { ...toast, visible: false } : toast,
      );
    case "remove":
      return state.filter((toast) => toast.id !== action.id);
    default:
      return state;
  }
}
