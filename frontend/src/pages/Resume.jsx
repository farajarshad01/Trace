import { useEffect, useRef, useState } from "react";

import Icon from "../components/Icon";
import RoleEditor from "../components/RoleEditor";
import { useToast } from "../components/Toast";
import Avatar from "../components/Avatar";
import { createRole, deleteRole, getCurrentResume, getRoles, uploadResume } from "../services/api";
import { entryParts, formatDate } from "../utils/format";


const SKILL_GROUPS = [
    ["skills", "Skills"],
    ["programming_languages", "Languages"],
    ["frameworks", "Frameworks"],
    ["libraries", "Libraries"],
    ["tools", "Tools"],
    ["databases", "Databases"],
];


function Timeline({ items, kind }) {
    return (
        <div className="timeline">
            {items.map((item, i) => {
                const e = entryParts(item, kind);

                return (
                    <div className="t-item" key={i}>
                        <h4>{e.title}</h4>
                        {(e.sub || e.when) && <div className="t-sub">{e.sub}{e.sub && e.when ? " · " : ""}<span>{e.when}</span></div>}
                        {e.text && <p>{e.text}</p>}
                    </div>
                );
            })}
        </div>
    );
}


export default function Resume() {
    const toast = useToast();
    const inputRef = useRef(null);

    const [resume, setResume] = useState(null);
    const [roles, setRoles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;

        Promise.all([getCurrentResume(), getRoles()])
            .then(([r, rs]) => { if (!cancelled) { setResume(r); setRoles(rs || []); } })
            .catch((err) => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, []);

    async function handleFile(file) {
        if (!file || uploading) return;

        if (!/\.(pdf|docx)$/i.test(file.name)) {
            setError("Please choose a PDF or DOCX file.");
            return;
        }

        setUploading(true);
        setError("");

        try {
            setResume(await uploadResume(file));
            toast.success("Resume updated");
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

    if (loading) return <div className="page"><div className="skeleton" style={{ height: 420, borderRadius: 22 }} /></div>;

    const p = resume?.structured_profile || {};
    const groups = SKILL_GROUPS.filter(([key]) => p[key]?.length);

    return (
        <div className="page">
            <header className="page-head">
                <div>
                    <div className="eyebrow">Resume</div>
                    <h1>Your profile</h1>
                    <p className="sub">What our AI understood from your resume. This is what every job is compared against.</p>
                </div>
            </header>

            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

            <div className="resume-layout">
                <aside className="resume-side">
                    <section className="card-pad glass strong">
                        <h2>Current resume</h2>

                        {resume ? (
                            <div className="file-ok" style={{ marginTop: 14 }}>
                                <span className="ok-icon"><Icon name="file" /></span>
                                <div style={{ minWidth: 0 }}>
                                    <strong>{resume.file_name}</strong>
                                    <span>Uploaded {formatDate(resume.created_at)}</span>
                                </div>
                            </div>
                        ) : <p className="hint">No resume uploaded yet.</p>}

                        <div className={`upload compact`} style={{ marginTop: resume ? 0 : 6 }}>
                            <input ref={inputRef} type="file" accept=".pdf,.docx" aria-label="Replace resume" disabled={uploading}
                                onChange={(e) => { handleFile(e.target.files?.[0]); e.target.value = ""; }} />
                            {uploading ? <><span className="spinner sm" /><span className="u-title">Analysing with AI…</span></> : <><Icon name="upload" size={18} /><span className="u-title">{resume ? "Replace resume" : "Upload resume"}</span></>}
                        </div>
                    </section>

                    <section className="card-pad glass strong">
                        <h2>Target roles</h2>
                        <p className="hint">Trace ranks jobs against these.</p>
                        <RoleEditor roles={roles} onAdd={addRole} onRemove={removeRole} suggestions={p.suggested_roles || []} />
                    </section>
                </aside>

                <section className="card-pad glass strong" style={{ marginTop: 0 }}>
                    {!resume ? (
                        <div className="empty" style={{ padding: "40px 12px" }}>
                            <div className="empty-icon"><Icon name="file" /></div>
                            <h3>Upload a resume to get started</h3>
                            <p>We'll extract your skills and experience so Trace can match you to jobs.</p>
                        </div>
                    ) : (
                        <>
                            <div className="profile-head">
                                <Avatar name={p.full_name || resume.file_name} round />
                                <div>
                                    <h2>{p.full_name || "Your profile"}</h2>
                                    {p.email && <span className="email"><Icon name="mail" />{p.email}</span>}
                                </div>
                            </div>

                            {p.summary && <p className="prose">{p.summary}</p>}

                            <div className="facts">
                                {p.total_years_experience !== null && p.total_years_experience !== undefined && (
                                    <span className="chip lg"><Icon name="briefcase" />{p.total_years_experience} yrs experience</span>
                                )}
                                <span className="chip lg neutral"><Icon name="sparkles" />{(p.skills || []).length} {(p.skills || []).length === 1 ? "skill" : "skills"}</span>
                                {p.certifications?.length > 0 && <span className="chip lg neutral"><Icon name="trophy" />{p.certifications.length} {p.certifications.length === 1 ? "certification" : "certifications"}</span>}
                            </div>

                            {groups.map(([key, label]) => (
                                <div className="group" key={key}>
                                    <div className="section-title">{label}</div>
                                    <div className="chips">{p[key].map((s) => <span className="chip" key={s}>{s}</span>)}</div>
                                </div>
                            ))}

                            {p.experience?.length > 0 && <div className="group"><div className="section-title">Experience</div><Timeline items={p.experience} kind="experience" /></div>}
                            {p.projects?.length > 0 && <div className="group"><div className="section-title">Projects</div><Timeline items={p.projects} kind="project" /></div>}
                            {p.education?.length > 0 && <div className="group"><div className="section-title">Education</div><Timeline items={p.education} kind="education" /></div>}

                            {p.certifications?.length > 0 && (
                                <div className="group">
                                    <div className="section-title">Certifications</div>
                                    <div className="chips">{p.certifications.map((c) => <span className="chip neutral" key={c}>{c}</span>)}</div>
                                </div>
                            )}
                        </>
                    )}
                </section>
            </div>
        </div>
    );
}
