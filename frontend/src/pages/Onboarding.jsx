import { useEffect, useRef, useState } from "react";

import Icon from "../components/Icon";
import Logo from "../components/Logo";
import RoleEditor from "../components/RoleEditor";
import { ThemeToggle } from "../components/Theme";
import { createRole, deleteRole, getCurrentResume, getRoles, uploadResume } from "../services/api";


const AI_STEPS = ["Reading your resume", "Extracting skills & experience", "Suggesting roles that fit you"];


export default function Onboarding({ onComplete }) {
    const [resume, setResume] = useState(null);
    const [roles, setRoles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [aiStep, setAiStep] = useState(0);
    const [over, setOver] = useState(false);
    const [error, setError] = useState("");
    const inputRef = useRef(null);

    useEffect(() => {
        let cancelled = false;

        Promise.all([getCurrentResume(), getRoles()])
            .then(([r, rs]) => {
                if (cancelled) return;

                setResume(r);
                setRoles(rs || []);
            })
            .catch((err) => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, []);

    // Purely cosmetic progress while the (single) AI request runs.
    useEffect(() => {
        if (!uploading) return undefined;

        setAiStep(0);

        const timer = setInterval(() => setAiStep((s) => Math.min(s + 1, AI_STEPS.length - 1)), 3500);

        return () => clearInterval(timer);
    }, [uploading]);

    async function processFile(file) {
        if (!file || uploading) return;

        if (!/\.(pdf|docx)$/i.test(file.name)) {
            setError("Please choose a PDF or DOCX file.");
            return;
        }

        setUploading(true);
        setError("");

        try {
            const uploaded = await uploadResume(file);

            setResume(uploaded);

            // Turn the AI's suggestions into target roles (the user can remove any).
            const existing = new Set(roles.map((r) => r.role_title.toLowerCase()));

            for (const title of uploaded.structured_profile?.suggested_roles || []) {
                if (existing.has(title.toLowerCase())) continue;

                try { await createRole(title); } catch { /* skip duplicates / failures */ }

                existing.add(title.toLowerCase());
            }

            setRoles((await getRoles()) || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setUploading(false);
        }
    }

    const addRole = async (title) => {
        try {
            await createRole(title);
            setRoles((await getRoles()) || []);
        } catch (err) {
            setError(err.message);
        }
    };

    const removeRole = async (role) => {
        setRoles((list) => list.filter((r) => r.id !== role.id));

        try {
            await deleteRole(role.id);
        } catch (err) {
            setError(err.message);
            setRoles((await getRoles()) || []);
        }
    };

    const step = resume ? 2 : 1;
    const profile = resume?.structured_profile;

    if (loading) return <div className="screen-center"><div className="spinner" /></div>;

    return (
        <main className="onb">
            <div style={{ position: "fixed", top: 18, right: 18 }}><ThemeToggle /></div>

            <div className="onb-logo"><Logo height={32} /></div>

            <div className="onb-head">
                <h1>{step === 1 ? "Let's get to know you" : <>Looking good, <span className="grad-text">here's your profile</span></>}</h1>
                <p>{step === 1 ? "Upload your resume and our AI will build your profile in seconds." : "Pick the roles you want Trace to hunt for."}</p>
            </div>

            <div className="stepper" aria-label="Progress">
                <div className={`s ${step === 1 ? "on" : "done"}`}><span className="n">{step > 1 ? <Icon name="check" strokeWidth={3} /> : 1}</span>Resume</div>
                <span className="line" />
                <div className={`s ${step === 2 ? "on" : ""}`}><span className="n">2</span>Target roles</div>
            </div>

            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

            <section className="card-pad glass strong">
                <h2>Your resume</h2>
                <p className="hint">PDF or DOCX, up to 5 MB.</p>

                {uploading ? (
                    <div className="ai-steps" role="status" aria-live="polite">
                        {AI_STEPS.map((label, i) => (
                            <div key={label} className={`ai-step ${i < aiStep ? "done" : i === aiStep ? "now" : ""}`}>
                                <span className="mk">{i < aiStep ? <Icon name="check" strokeWidth={3} /> : i === aiStep ? <i /> : null}</span>
                                {label}
                            </div>
                        ))}
                    </div>
                ) : (
                    <>
                        {resume && (
                            <div className="file-ok">
                                <span className="ok-icon"><Icon name="check" strokeWidth={3} /></span>
                                <div style={{ minWidth: 0 }}>
                                    <strong>{resume.file_name}</strong>
                                    <span>{profile?.skills?.length ? `${profile.skills.length} skills found` : "Profile created"}</span>
                                </div>
                            </div>
                        )}

                        <div
                            className={`upload ${over ? "over" : ""} ${resume ? "compact" : ""}`}
                            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
                            onDragLeave={() => setOver(false)}
                            onDrop={(e) => { e.preventDefault(); setOver(false); processFile(e.dataTransfer.files?.[0]); }}
                        >
                            <input ref={inputRef} type="file" accept=".pdf,.docx" aria-label="Upload resume"
                                onChange={(e) => { processFile(e.target.files?.[0]); e.target.value = ""; }} />

                            {resume ? (
                                <><Icon name="upload" size={18} /><span className="u-title">Upload a different resume</span></>
                            ) : (
                                <>
                                    <span className="u-icon"><Icon name="upload" /></span>
                                    <span className="u-title">Drop your resume here</span>
                                    <span className="u-sub">or click to browse</span>
                                </>
                            )}
                        </div>
                    </>
                )}
            </section>

            {resume && !uploading && (
                <section className="card-pad glass strong">
                    <h2>Target roles</h2>
                    <p className="hint">Trace ranks jobs against these. Add more, or remove any you don't want.</p>

                    <RoleEditor roles={roles} onAdd={addRole} onRemove={removeRole} suggestions={profile?.suggested_roles || []} />

                    <div className="cta-row">
                        <button type="button" className="btn btn-primary btn-lg btn-block" disabled={roles.length === 0} onClick={onComplete}>
                            Continue to dashboard <Icon name="arrow" />
                        </button>

                        {roles.length === 0 && <p className="skip">Add at least one role to continue, or <button type="button" onClick={onComplete}>skip for now</button>.</p>}
                    </div>
                </section>
            )}
        </main>
    );
}
