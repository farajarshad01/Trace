import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ApplicationTracker from "../components/ApplicationTracker";
import Icon from "../components/Icon";
import JobDrawer from "../components/JobDrawer";
import { useToast } from "../components/Toast";
import TriageDeck from "../components/TriageDeck";
import TriageQueue from "../components/TriageQueue";
import TriageSummary from "../components/TriageSummary";
import {
    deleteApplication, dismissJob, getApplications, getJobs, getRoles, restoreJob, updateApplication,
} from "../services/api";


const DEFAULT_FILTERS = { query: "", company: "all", minMatch: "0", sort: "match" };
const STRONG_MATCH = 70;
const MAX_SEGMENTS = 12;


function matchesFilters(job, filters) {
    if (filters.company !== "all" && job.company_name !== filters.company) return false;
    if (Number(filters.minMatch) > 0 && (job.match_score ?? -1) < Number(filters.minMatch)) return false;

    const q = filters.query.trim().toLowerCase();

    if (!q) return true;

    return [job.title, job.company_name, job.location, ...(job.required_skills || [])]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q));
}


function sortJobs(list, sort) {
    // Array.sort is stable, so ties keep the API's order (newest first).
    if (sort === "newest") return [...list].sort((a, b) => new Date(b.first_seen_at) - new Date(a.first_seen_at));

    return [...list].sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1));
}


export default function Dashboard({ onNavigate }) {
    const toast = useToast();

    const [jobs, setJobs] = useState([]);
    const [hidden, setHidden] = useState([]);
    const [applications, setApplications] = useState([]);
    const [roles, setRoles] = useState([]);

    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const [filters, setFilters] = useState(DEFAULT_FILTERS);
    const [view, setView] = useState("queue");          // "queue" | "hidden"
    const [cursorId, setCursorId] = useState(null);
    const [skipped, setSkipped] = useState([]);         // session only: ids pushed to the back
    const [history, setHistory] = useState([]);         // session only: for Undo

    const [selected, setSelected] = useState(null);     // job drawer
    const [tracking, setTracking] = useState(null);     // tracker modal

    const load = useCallback(async ({ silent = false } = {}) => {
        if (silent) setRefreshing(true); else setLoading(true);

        setError("");

        try {
            const [jobList, appList, hiddenList, roleList] = await Promise.all([
                getJobs(),
                getApplications(),
                // Optional pieces degrade quietly (e.g. an older backend).
                getJobs(200, { dismissed: true }).catch(() => []),
                getRoles().catch(() => []),
            ]);

            setJobs(jobList || []);
            setApplications(appList || []);
            setHidden(hiddenList || []);
            setRoles(roleList || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    // ── the queue ───────────────────────────────────────────────────────
    const trackedIds = useMemo(() => new Set(applications.map((a) => a.job_id)), [applications]);

    // The inbox: jobs you have not decided on (tracked jobs live in the pipeline).
    const inbox = useMemo(() => jobs.filter((j) => !trackedIds.has(j.id)), [jobs, trackedIds]);
    const pool = view === "hidden" ? hidden : inbox;

    const queue = useMemo(() => {
        const list = sortJobs(pool.filter((j) => matchesFilters(j, filters)), filters.sort);

        if (view === "hidden") return list;

        const later = new Set(skipped);

        return [
            ...list.filter((j) => !later.has(j.id)),
            ...skipped.map((id) => list.find((j) => j.id === id)).filter(Boolean),
        ];
    }, [pool, filters, view, skipped]);

    const companies = useMemo(() => [...new Set(pool.map((j) => j.company_name))].sort(), [pool]);
    const filtering = Boolean(filters.query || filters.company !== "all" || filters.minMatch !== "0");

    const found = queue.findIndex((j) => j.id === cursorId);
    const index = found === -1 ? 0 : found;
    const current = queue[index] ?? null;

    const reviewed = history.filter((h) => h.type !== "skip").length;
    const total = reviewed + inbox.length;
    const strongLeft = inbox.filter((j) => (j.match_score ?? 0) >= STRONG_MATCH).length;
    const pending = jobs.filter((j) => !j.analyzed).length;

    // ── decisions ───────────────────────────────────────────────────────
    // After deciding on the job on screen, show the next one. If the job
    // decided on is NOT the one on screen (a toast action), leave the screen alone.
    const advanceFrom = (job) => {
        if (!current || current.id !== job.id) return;

        const i = queue.findIndex((j) => j.id === job.id);
        const next = queue[i + 1] ?? queue[i - 1] ?? null;

        setCursorId(next ? next.id : null);
    };

    async function hideJob(job = current) {
        if (!job || view !== "queue") return;

        const entry = { type: "hide", job };

        advanceFrom(job);
        setSelected(null);
        setJobs((l) => l.filter((j) => j.id !== job.id));
        setHidden((l) => [job, ...l]);
        setHistory((h) => [...h, entry]);

        try {
            await dismissJob(job.id);
            toast.success("Job hidden", { action: { label: "Undo", onClick: () => latest.current.undo(entry) } });
        } catch (err) {
            setHidden((l) => l.filter((j) => j.id !== job.id));
            setJobs((l) => [job, ...l]);
            setHistory((h) => h.filter((e) => e !== entry));
            setCursorId(job.id);
            toast.error(err.message);
        }
    }

    async function trackJob(job = current, status = "Saved") {
        if (!job || view !== "queue") return;

        const entry = { type: "track", job };

        advanceFrom(job);
        setSelected(null);
        setApplications((l) => [{ id: `pending-${job.id}`, job_id: job.id, status, notes: "", job }, ...l.filter((a) => a.job_id !== job.id)]);
        setHistory((h) => [...h, entry]);

        try {
            const saved = await updateApplication(job.id, status, "");

            if (saved) setApplications((l) => l.map((a) => (a.job_id === job.id ? saved : a)));

            toast.success(status === "Applied" ? "Marked as applied" : "Saved to your pipeline", {
                action: { label: "Undo", onClick: () => latest.current.undo(entry) },
            });
        } catch (err) {
            setApplications((l) => l.filter((a) => a.job_id !== job.id));
            setHistory((h) => h.filter((e) => e !== entry));
            setCursorId(job.id);
            toast.error(err.message);
        }
    }

    function applyJob(job = current) {
        if (!job) return;

        window.open(job.original_url, "_blank", "noopener,noreferrer");

        if (view === "queue") {
            toast.success("Opened the posting", {
                action: { label: "Mark applied", onClick: () => latest.current.trackJob(job, "Applied") },
            });
        }
    }

    function skipJob(job = current) {
        if (!job || view !== "queue" || queue.length < 2) return;

        const next = queue[index + 1] ?? queue[0];

        setSkipped((s) => [...s.filter((id) => id !== job.id), job.id]);
        setHistory((h) => [...h, { type: "skip", job }]);
        setCursorId(next.id);
    }

    async function restoreHidden(job = current) {
        if (!job || view !== "hidden") return;

        advanceFrom(job);
        setHidden((l) => l.filter((j) => j.id !== job.id));
        setJobs((l) => [job, ...l.filter((j) => j.id !== job.id)]);

        try {
            await restoreJob(job.id);
            toast.success("Job restored to your inbox");
        } catch (err) {
            setJobs((l) => l.filter((j) => j.id !== job.id));
            setHidden((l) => [job, ...l]);
            setCursorId(job.id);
            toast.error(err.message);
        }
    }

    async function undo(entry = history[history.length - 1]) {
        if (!entry) return;

        const { type, job } = entry;

        setHistory((h) => h.filter((e) => e !== entry));
        setView("queue");
        setCursorId(job.id);

        if (type === "skip") {
            setSkipped((s) => s.filter((id) => id !== job.id));
            return;
        }

        if (type === "hide") {
            setHidden((l) => l.filter((j) => j.id !== job.id));
            setJobs((l) => [job, ...l.filter((j) => j.id !== job.id)]);

            try { await restoreJob(job.id); } catch (err) { toast.error(err.message); load({ silent: true }); }

            return;
        }

        setApplications((l) => l.filter((a) => a.job_id !== job.id));

        try { await deleteApplication(job.id); } catch (err) { toast.error(err.message); load({ silent: true }); }
    }

    const move = (delta) => {
        const target = queue[Math.min(Math.max(index + delta, 0), queue.length - 1)];

        if (target) setCursorId(target.id);
    };

    // Changing sort or filters starts again from the top of the new order.
    function updateFilters(next) {
        setFilters(next);
        setCursorId(null);
    }

    function toggleHidden() {
        setView((v) => (v === "hidden" ? "queue" : "hidden"));
        setCursorId(null);
        setFilters(DEFAULT_FILTERS);
    }

    async function handleTrackerClose(change) {
        const job = tracking;

        if (change && job && current && current.id === job.id) {
            const i = queue.findIndex((j) => j.id === job.id);

            setCursorId((queue[i + 1] ?? queue[i - 1])?.id ?? null);
        }

        setTracking(null);

        if (change) {
            try { setApplications((await getApplications()) || []); } catch { /* keep the old list */ }
        }
    }

    // ── keyboard ────────────────────────────────────────────────────────
    // Handlers are re-created every render; the listener reads the latest ones.
    const latest = useRef({});
    latest.current = { hideJob, trackJob, applyJob, skipJob, restoreHidden, undo, move, current, view, selected, tracking };

    useEffect(() => {
        function onKey(event) {
            if (event.metaKey || event.ctrlKey || event.altKey) return;

            const el = event.target;

            if (el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;

            const h = latest.current;

            if (h.selected || h.tracking) return;

            const key = event.key.toLowerCase();
            const queueMode = h.view === "queue";
            const handlers = {
                h: queueMode && (() => h.hideJob()),
                t: queueMode && (() => h.trackJob()),
                s: queueMode && (() => h.skipJob()),
                z: queueMode && (() => h.undo()),
                r: !queueMode && (() => h.restoreHidden()),
                a: () => h.applyJob(),
                d: () => h.current && setSelected(h.current),
                arrowleft: () => h.move(-1),
                arrowright: () => h.move(1),
            };

            const run = handlers[key];

            if (run && (h.current || key === "z")) {
                event.preventDefault();
                run();
            }
        }

        window.addEventListener("keydown", onKey);

        return () => window.removeEventListener("keydown", onKey);
    }, []);

    // ── render ──────────────────────────────────────────────────────────
    const segments = Math.min(Math.max(total, 1), MAX_SEGMENTS);
    const done = total ? Math.min(segments, Math.round((reviewed / total) * segments)) : 0;

    function renderEmpty() {
        if (view === "hidden") {
            return (
                <div className="empty glass">
                    <div className="empty-icon"><Icon name="eyeoff" /></div>
                    <h3>{filtering ? "No hidden jobs match" : "Nothing hidden"}</h3>
                    <p>Jobs you mark "Not relevant" are kept here so you can bring them back.</p>
                    <button type="button" className="btn btn-glass" onClick={toggleHidden}>Back to inbox</button>
                </div>
            );
        }

        if (filtering && inbox.length > 0) {
            return (
                <div className="empty glass">
                    <div className="empty-icon"><Icon name="search" /></div>
                    <h3>No jobs match those filters</h3>
                    <p>Try a broader search or a lower minimum match.</p>
                    <button type="button" className="btn btn-glass" onClick={() => updateFilters(DEFAULT_FILTERS)}>Clear filters</button>
                </div>
            );
        }

        if (jobs.length + hidden.length + applications.length > 0) {
            return (
                <div className="empty glass">
                    <div className="empty-icon"><Icon name="check" /></div>
                    <h3>You're all caught up</h3>
                    <p>Nothing left to decide on. New roles appear after the next hourly check.</p>

                    <div className="empty-actions">
                        <button type="button" className="btn btn-primary" onClick={() => onNavigate("applications")}>Open your pipeline <Icon name="arrow" /></button>
                        {hidden.length > 0 && <button type="button" className="btn btn-glass" onClick={toggleHidden}><Icon name="eyeoff" /> Review hidden ({hidden.length})</button>}
                    </div>
                </div>
            );
        }

        return (
            <div className="empty glass">
                <div className="empty-icon"><Icon name="building" /></div>
                <h3>No matching jobs yet</h3>
                <p>Trace only keeps jobs whose titles match your target roles. Add companies to watch, or check your roles. New jobs appear after the next hourly check.</p>

                <div className="empty-actions">
                    <button type="button" className="btn btn-primary" onClick={() => onNavigate("companies")}><Icon name="plus" /> Add companies</button>
                    <button type="button" className="btn btn-glass" onClick={() => onNavigate("resume")}><Icon name="target" /> Edit target roles</button>
                </div>
            </div>
        );
    }

    return (
        <div className="triage">
            <TriageSummary
                reviewed={reviewed}
                total={total}
                pipeline={applications.length}
                hidden={hidden.length}
                skipped={skipped.filter((id) => inbox.some((j) => j.id === id)).length}
                strongLeft={strongLeft}
                view={view}
                roles={roles}
                pending={pending}
                refreshing={refreshing}
                onRefresh={() => load({ silent: true })}
                onToggleHidden={toggleHidden}
                onPipeline={() => onNavigate("applications")}
                onEditRoles={() => onNavigate("resume")}
            />

            <section className="tri-stage" aria-busy={loading}>
                {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

                {loading ? (
                    <div className="tri-skel"><div className="skeleton" /><div className="skeleton tall" /></div>
                ) : current ? (
                    <>
                        <div className="tri-progress">
                            {view === "queue" && (
                                <div className="tri-segs" aria-hidden="true">
                                    {Array.from({ length: segments }, (_, i) => <i key={i} className={i < done ? "c" : i === done ? "now" : ""} />)}
                                </div>
                            )}

                            <div className="tri-progress-row">
                                <span>{view === "hidden" ? "Hidden job" : "Role"} {index + 1} of {queue.length}</span>

                                <label className="tri-sort">
                                    Sorted by
                                    <select value={filters.sort} onChange={(e) => { updateFilters({ ...filters, sort: e.target.value }); e.target.blur(); }} aria-label="Sort order">
                                        <option value="match">Best match</option>
                                        <option value="newest">Newest</option>
                                    </select>
                                </label>
                            </div>
                        </div>

                        <p className="sr-only" role="status">{`Showing ${current.title} at ${current.company_name}, ${index + 1} of ${queue.length}`}</p>

                        <TriageDeck
                            job={current}
                            mode={view}
                            peeks={Math.min(queue.length - 1, 2)}
                            canSkip={queue.length > 1}
                            canGoBack={index > 0}
                            canGoNext={index < queue.length - 1}
                            canUndo={history.length > 0}
                            onHide={() => hideJob()}
                            onTrack={() => trackJob()}
                            onApply={() => applyJob()}
                            onSkip={() => skipJob()}
                            onRestore={() => restoreHidden()}
                            onDetails={() => setSelected(current)}
                            onUndo={() => undo()}
                            onPrev={() => move(-1)}
                            onNext={() => move(1)}
                        />
                    </>
                ) : renderEmpty()}
            </section>

            <TriageQueue
                jobs={queue}
                currentId={current?.id}
                view={view}
                filters={filters}
                onFilters={updateFilters}
                companies={companies}
                filtering={filtering}
                onClear={() => updateFilters(DEFAULT_FILTERS)}
                onSelect={setCursorId}
            />

            {selected && (
                <JobDrawer
                    job={selected}
                    application={applications.find((a) => a.job_id === selected.id)}
                    onClose={() => setSelected(null)}
                    onTrack={(job) => setTracking(job)}
                    onDismiss={view === "queue" ? (job) => hideJob(job) : undefined}
                />
            )}

            {tracking && (
                <ApplicationTracker
                    job={tracking}
                    initialApplication={applications.find((a) => a.job_id === tracking.id && !String(a.id).startsWith("pending")) ?? null}
                    onClose={handleTrackerClose}
                />
            )}
        </div>
    );
}
