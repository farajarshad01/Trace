import { useCallback, useEffect, useMemo, useState } from "react";

import ApplicationTracker from "../components/ApplicationTracker";
import Avatar from "../components/Avatar";
import Icon from "../components/Icon";
import { useToast } from "../components/Toast";
import { getApplications, updateApplication } from "../services/api";
import { STATUSES, formatDate, statusClass } from "../utils/format";


export default function Applications({ onNavigate }) {
    const toast = useToast();

    const [applications, setApplications] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [view, setView] = useState("board");
    const [editing, setEditing] = useState(null);
    const [dragId, setDragId] = useState(null);
    const [dropCol, setDropCol] = useState(null);

    const load = useCallback(async () => {
        try {
            setApplications((await getApplications()) || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const grouped = useMemo(() => {
        const map = Object.fromEntries(STATUSES.map((s) => [s, []]));

        for (const app of applications) (map[app.status] || map.Saved).push(app);

        return map;
    }, [applications]);

    async function moveTo(app, status) {
        if (!app || app.status === status) return;

        const previous = applications;

        setApplications((list) => list.map((a) => (a.job_id === app.job_id ? { ...a, status } : a)));

        try {
            await updateApplication(app.job_id, status, app.notes || "");
            toast.success(`Moved to ${status}`);
        } catch (err) {
            setApplications(previous);
            toast.error(err.message);
        }
    }

    function onDrop(event, status) {
        event.preventDefault();

        const app = applications.find((a) => a.job_id === dragId);

        setDropCol(null);
        setDragId(null);
        moveTo(app, status);
    }

    async function handleClose(change) {
        setEditing(null);

        if (change) await load();
    }

    const jobOf = (app) => app.job || { id: app.job_id, company_name: "Unknown company", title: "Job no longer available", original_url: "#" };

    return (
        <div className="page">
            <header className="page-head">
                <div>
                    <div className="eyebrow">Applications</div>
                    <h1>Your pipeline</h1>
                    <p className="sub">{applications.length ? "Drag cards between columns, or open one to update its status and notes." : "Track jobs from your dashboard and they'll show up here."}</p>
                </div>

                <div className="page-actions">
                    <div className="segmented" role="tablist" aria-label="View">
                        <button type="button" role="tab" aria-selected={view === "board"} className={view === "board" ? "on" : ""} onClick={() => setView("board")}><Icon name="columns" />Board</button>
                        <button type="button" role="tab" aria-selected={view === "list"} className={view === "list" ? "on" : ""} onClick={() => setView("list")}><Icon name="list" />List</button>
                    </div>
                </div>
            </header>

            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

            {loading ? (
                <div className="board">{STATUSES.map((s) => <div key={s} className="skeleton" style={{ height: 280, borderRadius: 22 }} />)}</div>
            ) : applications.length === 0 ? (
                <div className="empty glass">
                    <div className="empty-icon"><Icon name="clipboard" /></div>
                    <h3>Nothing tracked yet</h3>
                    <p>Open a job on your dashboard and hit <b>Track</b> to start following it through the hiring process.</p>
                    <button type="button" className="btn btn-primary" onClick={() => onNavigate("dashboard")}>Browse jobs <Icon name="arrow" /></button>
                </div>
            ) : view === "board" ? (
                <div className="board">
                    {STATUSES.map((status) => (
                        <section
                            key={status}
                            className={`col glass ${statusClass(status)} ${dropCol === status ? "drop" : ""}`}
                            onDragOver={(e) => { e.preventDefault(); setDropCol(status); }}
                            onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDropCol(null); }}
                            onDrop={(e) => onDrop(e, status)}
                            aria-label={`${status} column`}
                        >
                            <div className={`col-head ${statusClass(status)}`}>
                                <span className="dot" />{status}
                                <span className="count">{grouped[status].length}</span>
                            </div>

                            {grouped[status].map((app) => {
                                const job = jobOf(app);

                                return (
                                    <div
                                        key={app.id}
                                        className={`app-card glass interactive ${dragId === app.job_id ? "dragging" : ""}`}
                                        draggable
                                        role="button"
                                        tabIndex={0}
                                        onDragStart={(e) => { setDragId(app.job_id); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(app.job_id)); }}
                                        onDragEnd={() => { setDragId(null); setDropCol(null); }}
                                        onClick={() => setEditing(app)}
                                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setEditing(app); } }}
                                    >
                                        <span className="ac-company">{job.company_name}</span>
                                        <span className="ac-title">{job.title}</span>
                                        {app.notes && <span className="ac-note">{app.notes}</span>}
                                        <span className="ac-meta"><Icon name="calendar" />{app.applied_at ? `Applied ${formatDate(app.applied_at)}` : `Saved ${formatDate(app.created_at)}`}</span>
                                    </div>
                                );
                            })}

                            {grouped[status].length === 0 && <div className="col-empty">Drop a card here</div>}
                        </section>
                    ))}
                </div>
            ) : (
                <div className="app-list">
                    {applications.map((app) => {
                        const job = jobOf(app);

                        return (
                            <button key={app.id} type="button" className="app-row glass interactive" onClick={() => setEditing(app)}>
                                <Avatar name={job.company_name} />

                                <div className="ar-main">
                                    <div className="jc-company">{job.company_name}</div>
                                    <h3>{job.title}</h3>
                                    {app.notes && <div className="ar-note">{app.notes}</div>}
                                </div>

                                <span className={`status-pill ${statusClass(app.status)}`}><span className="dot" />{app.status}</span>
                            </button>
                        );
                    })}
                </div>
            )}

            {editing && <ApplicationTracker job={jobOf(editing)} initialApplication={editing} onClose={handleClose} />}
        </div>
    );
}
