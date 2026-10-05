import { useCallback, useEffect, useState } from "react";

import Background from "./components/Background";
import Icon from "./components/Icon";
import Logo from "./components/Logo";
import Navbar, { NAV_ITEMS } from "./components/Navbar";
import { ThemeToggle } from "./components/Theme";
import Applications from "./pages/Applications";
import Companies from "./pages/Companies";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Resume from "./pages/Resume";
import { getCurrentResume } from "./services/api";
import { supabase } from "./services/supabase";


const PAGE_IDS = NAV_ITEMS.map((item) => item.id);

const pageFromHash = () => {
    const id = window.location.hash.replace(/^#\/?/, "");

    return PAGE_IDS.includes(id) ? id : "dashboard";
};

// Module-level so React StrictMode's double-invoked effect (dev) cannot
// exchange the one-time OAuth code twice.
let codeExchange = null;

function exchangeOnce(code) {
    if (!codeExchange) codeExchange = supabase.auth.exchangeCodeForSession(code);

    return codeExchange;
}


function Splash({ children }) {
    return (
        <div className="screen-center">
            <Logo variant="mark" height={44} />
            {children}
        </div>
    );
}


function App() {
    const [session, setSession] = useState(null);
    const [authLoading, setAuthLoading] = useState(true);
    const [profile, setProfile] = useState({ status: "idle" });
    const [retry, setRetry] = useState(0);
    const [page, setPage] = useState(pageFromHash);

    // ── auth ────────────────────────────────────────────────────────────
    useEffect(() => {
        let active = true;

        async function init() {
            const url = new URL(window.location.href);
            const code = url.searchParams.get("code");

            if (code) {
                // Remove the one-time code from the address bar immediately.
                // Previously it stayed there on failure, so a page refresh
                // retried an already-used code and logged the user out.
                url.searchParams.delete("code");
                window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);

                try {
                    await exchangeOnce(code);
                } catch (err) {
                    console.error("OAuth code exchange failed:", err);
                }
            } else if (codeExchange) {
                await codeExchange.catch(() => {});
            }

            const { data } = await supabase.auth.getSession();

            if (active) {
                setSession(data.session ?? null);
                setAuthLoading(false);
            }
        }

        init().catch((err) => {
            console.error("Authentication initialization failed:", err);

            if (active) setAuthLoading(false);
        });

        const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
            if (!active) return;

            // Token refreshes and tab-focus events hand us a fresh object for
            // the same user; keeping the old one avoids re-running effects.
            setSession((prev) => (prev?.user?.id === next?.user?.id && prev?.access_token === next?.access_token ? prev : next ?? null));
        });

        return () => {
            active = false;
            listener.subscription.unsubscribe();
        };
    }, []);

    // ── profile / onboarding check: once per user, not per session object ─
    const userId = session?.user?.id;

    useEffect(() => {
        if (!userId) {
            setProfile({ status: "idle" });
            return undefined;
        }

        let cancelled = false;

        setProfile({ status: "checking" });

        getCurrentResume()
            .then((resume) => { if (!cancelled) setProfile({ status: resume ? "ready" : "onboarding" }); })
            .catch((err) => { if (!cancelled) setProfile({ status: "error", message: err.message }); });

        return () => { cancelled = true; };
    }, [userId, retry]);

    // ── hash navigation (back button + refresh keep your place) ─────────
    useEffect(() => {
        const onHash = () => setPage(pageFromHash());

        window.addEventListener("hashchange", onHash);

        return () => window.removeEventListener("hashchange", onHash);
    }, []);

    const navigate = useCallback((id) => {
        window.location.hash = `/${id}`;
        setPage(id);
        window.scrollTo({ top: 0 });
    }, []);

    async function handleLogout() {
        await supabase.auth.signOut();
        setSession(null);
        setProfile({ status: "idle" });
        window.location.hash = "";
    }

    // ── render ──────────────────────────────────────────────────────────
    let content;

    if (authLoading) {
        content = <Splash><div className="spinner" /></Splash>;
    } else if (!session) {
        content = <Login />;
    } else if (profile.status === "idle" || profile.status === "checking") {
        content = <Splash><div className="spinner" /></Splash>;
    } else if (profile.status === "error") {
        content = (
            <div className="screen-center">
                <div className="glass strong" style={{ padding: 32, maxWidth: 440, textAlign: "center" }}>
                    <div className="empty-icon" style={{ width: 56, height: 56, margin: "0 auto 16px", display: "grid", placeItems: "center", borderRadius: 18, background: "var(--bad-bg)", color: "var(--bad)" }}><Icon name="alert" size={26} /></div>
                    <h3 style={{ marginBottom: 8 }}>We couldn't load your account</h3>
                    <p style={{ color: "var(--ink-2)", marginBottom: 20 }}>{profile.message}</p>

                    <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                        <button type="button" className="btn btn-primary" onClick={() => setRetry((n) => n + 1)}><Icon name="refresh" /> Try again</button>
                        <button type="button" className="btn btn-glass" onClick={handleLogout}>Sign out</button>
                    </div>
                </div>

                <div style={{ position: "fixed", top: 18, right: 18 }}><ThemeToggle /></div>
            </div>
        );
    } else if (profile.status === "onboarding") {
        content = <Onboarding onComplete={() => { setProfile({ status: "ready" }); navigate("dashboard"); }} />;
    } else {
        content = (
            <>
                <Navbar page={page} onNavigate={navigate} user={session.user} onLogout={handleLogout} />

                {page === "dashboard" && <Dashboard onNavigate={navigate} />}
                {page === "companies" && <Companies />}
                {page === "applications" && <Applications onNavigate={navigate} />}
                {page === "resume" && <Resume />}
            </>
        );
    }

    return (
        <>
            <Background />
            {content}
        </>
    );
}


export default App;
