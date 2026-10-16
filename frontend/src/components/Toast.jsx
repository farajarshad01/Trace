import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import Icon from "./Icon";


const ToastContext = createContext({ success: () => { }, error: () => { } });


export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const nextId = useRef(1);

    const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);

    // options.action = { label, onClick } adds a button (e.g. "Undo") and keeps
    // the toast on screen a little longer.
    const push = useCallback((type, message, options = {}) => {
        const id = nextId.current++;

        setToasts((list) => [...list.slice(-3), { id, type, message, action: options.action }]);

        const ms = options.action ? 7000 : type === "error" ? 6000 : 3600;

        setTimeout(() => dismiss(id), ms);
    }, [dismiss]);

    const api = useMemo(() => ({
        success: (message, options) => push("success", message, options),
        error: (message, options) => push("error", message, options),
    }), [push]);

    return (
        <ToastContext.Provider value={api}>
            {children}

            <div className="toasts" role="status" aria-live="polite">
                {toasts.map((t) => (
                    <div key={t.id} className={`toast glass strong ${t.type}`}>
                        <span className="t-icon"><Icon name={t.type === "error" ? "x" : "check"} strokeWidth={3} /></span>
                        {t.message}

                        {t.action && (
                            <button type="button" className="t-action" onClick={() => { t.action.onClick(); dismiss(t.id); }}>
                                {t.action.label}
                            </button>
                        )}
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}


export const useToast = () => useContext(ToastContext);
