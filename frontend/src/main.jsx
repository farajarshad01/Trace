import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ThemeProvider } from "./components/Theme";
import { ToastProvider } from "./components/Toast";
import "./index.css";


createRoot(document.getElementById("root")).render(
    <StrictMode>
        <ThemeProvider>
            <ToastProvider>
                <App />
            </ToastProvider>
        </ThemeProvider>
    </StrictMode>
);
