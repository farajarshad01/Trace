import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import Icon from "./Icon";


const ToastContext = createContext({ success: () => {}, error: () => {} });


export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const nextId = useRef(1);

    const push = useCallback((type, message) => {
        const id = nextId.current++;

        setToasts((list) => [...list.slice(-3), { id, type, message }]);

        setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), type === "error" ? 6000 : 3600);
    }, []);

    const api = useMemo(() => ({
        success: (message) => push("success", message),
        error: (message) => push("error", message),
    }), [push]);

    return (
        <ToastContext.Provider value={api}>
            {children}

            <div className="toasts" role="status" aria-live="polite">
                {toasts.map((t) => (
                    <div key={t.id} className={`toast glass strong ${t.type}`}>
                        <span className="t-icon"><Icon name={t.type === "error" ? "x" : "check"} strokeWidth={3} /></span>
                        {t.message}
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}


export const useToast = () => useContext(ToastContext);
