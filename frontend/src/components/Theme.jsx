import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import Icon from "./Icon";


const KEY = "trace-theme";

const ThemeContext = createContext({ theme: "light", toggle: () => {} });


function initialTheme() {
    try {
        const stored = localStorage.getItem(KEY);

        if (stored === "light" || stored === "dark") return stored;
    } catch { /* storage unavailable */ }

    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}


export function ThemeProvider({ children }) {
    const [theme, setTheme] = useState(initialTheme);

    useEffect(() => {
        document.documentElement.dataset.theme = theme;
    }, [theme]);

    const toggle = useCallback(() => {
        setTheme((current) => {
            const next = current === "dark" ? "light" : "dark";

            try { localStorage.setItem(KEY, next); } catch { /* ignore */ }

            return next;
        });
    }, []);

    const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}


export const useTheme = () => useContext(ThemeContext);


export function ThemeToggle() {
    const { theme, toggle } = useTheme();
    const dark = theme === "dark";

    return (
        <button
            type="button"
            className="btn btn-ghost btn-icon theme-toggle"
            onClick={toggle}
            aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
            title={dark ? "Light theme" : "Dark theme"}
        >
            <Icon name={dark ? "sun" : "moon"} />
        </button>
    );
}
