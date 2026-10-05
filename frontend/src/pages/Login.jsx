import { useState } from "react";

import Icon from "../components/Icon";
import Logo from "../components/Logo";
import { ThemeToggle } from "../components/Theme";
import ScoreRing from "../components/ScoreRing";
import Avatar from "../components/Avatar";
import { supabase } from "../services/supabase";


function GoogleMark() {
    return (
        <svg viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
        </svg>
    );
}


export default function Login() {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function handleGoogleLogin() {
        setLoading(true);
        setError("");

        const { error: authError } = await supabase.auth.signInWithOAuth({ provider: "google" });

        if (authError) {
            console.error("Google login error:", authError);
            setError(authError.message);
            setLoading(false);
        }
    }

    return (
        <main className="auth">
            <div style={{ position: "fixed", top: 18, right: 18 }}><ThemeToggle /></div>

            <section className="auth-hero">
                <Logo height={36} />

                <h1>Your job search,<br /><span className="grad-text">on autopilot.</span></h1>

                <p className="lead">
                    Upload your resume once. Trace watches the career pages you care about and
                    ranks every new opening against your skills — automatically, every hour.
                </p>

                <ul className="auth-features">
                    <li><span className="f-icon"><Icon name="file" /></span>AI reads your resume and builds your profile</li>
                    <li><span className="f-icon"><Icon name="zap" /></span>New roles are found and analysed for you</li>
                    <li><span className="f-icon"><Icon name="clipboard" /></span>Track every application and note in one place</li>
                </ul>

                <div className="auth-visual" aria-hidden="true">
                    <div className="mini-job glass strong a">
                        <Avatar name="Acme Labs" size="sm" />
                        <div><div className="t">Backend Engineer</div><div className="c">Acme Labs · Remote</div></div>
                        <ScoreRing value={92} size={44} stroke={4} />
                    </div>

                    <div className="mini-job glass strong b">
                        <Avatar name="Nimbus" size="sm" />
                        <div><div className="t">Data Engineer</div><div className="c">Nimbus · Karachi</div></div>
                        <ScoreRing value={74} size={44} stroke={4} />
                    </div>
                </div>
            </section>

            <section className="auth-card glass strong">
                <h2>Welcome to Trace</h2>
                <p className="sub">Sign in to start tracking roles that fit you.</p>

                {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

                <button type="button" className="btn btn-google btn-block" onClick={handleGoogleLogin} disabled={loading}>
                    {loading ? <span className="spinner sm" /> : <GoogleMark />}
                    {loading ? "Redirecting…" : "Continue with Google"}
                </button>

                <p className="fine">We only use your account to sign you in.</p>

                <div className="steps-mini">
                    <div><b>1</b>Upload your resume</div>
                    <div><b>2</b>Add companies you'd love to work at</div>
                    <div><b>3</b>Review matches and track applications</div>
                </div>
            </section>
        </main>
    );
}
