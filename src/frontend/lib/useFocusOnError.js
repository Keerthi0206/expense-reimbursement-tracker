import { useRef, useEffect } from "react";

// moves focus to the returned ref's element whenever `error` becomes truthy
// pair with role="alert" on the banner -- announces to screen readers too
export function useFocusOnError(error) {
  const ref = useRef(null);
  useEffect(() => {
    if (error && ref.current) {
      ref.current.focus();
    }
  }, [error]);
  return ref;
}
