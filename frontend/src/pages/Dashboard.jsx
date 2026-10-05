import { useCallback, useEffect, useMemo, useState } from "react";

import ApplicationTracker from "../components/ApplicationTracker";
import Icon from "../components/Icon";
import JobCard from "../components/JobCard";
import JobDrawer from "../components/JobDrawer";
import JobFilters from "../components/JobFilters";
import { getApplications, getJobs } from "../services/api";


const DEFAULT_FILTERS = { query: "", company: "all", minMatch: "0", sort: "match" };


export default function Dashboard({ onNavigate }) {
    const [jobs, setJobs] = useState([]);
    const [applications, setApplications] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [filters, setFilters] = useState(DEFAULT_FILTERS);
    const [selected, setSelected] = useState(null);
    const [tracking, setTracking] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");

        try {
            const [jobList, appList] = await Promise.all([getJobs(), getApplications()]);

            setJobs(jobList || []);
            setApplications(appList || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const appByJob = useMemo(() => new Map(applications.map((a) => [a.job_id, a])), [applications]);
    const companies = useMemo(() => [...new Set(jobs.map((j) => j.company_name))].sort(), [jobs]);

    const visible = useMemo(() => {
        const q = filters.query.trim().toLowerCase();
        const min = Number(filters.minMatch);

        const list = jobs.filter((job) => {
            if (filters.company !== "all" && job.company_name !== filters.company) return false;
            if (min > 0 && (job.match_score ?? -1) < min) return false;

            if (!q) return true;

            return [job.title, job.company_name, job.location, ...(job.required_skills || [])]
                .filter(Boolean)
                .some((value) => String(value).toLowerCase().includes(q));
        });

        if (filters.sort === "newest") {
            return [...list].sort((a, b) => new Date(b.first_seen_at) - new Date(a.first_seen_at));
        }

        // Best match first, unscored last. Array.sort is stable, so ties keep
        // the API's order (newest first).
        return [...list].sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1));
    }, [jobs, filters]);

    const stats = useMemo(() => ({
        found: jobs.length,
        strong: jobs.filter((j) => (j.match_score ?? 0) >= 70).length,
        tracked: applications.length,
        interviews: applications.filter((a) => a.status === "Interview").length,
    }), [jobs, applications]);

    const pending = jobs.filter((j) => !j.analyzed).length;
    const filtering = filters.query || filters.company !== "all" || filters.minMatch !== "0";

    async function handleTrackerClose(change) {
        setTracking(null);

        if (change) {
            try { setApplications((await getApplications()) || []); } catch { /* keep the old list */ }
        }
    }

    return (
        <div className="page">
            <header className="page-head">
                <div>
                    <div className="eyebrow">Dashboard</div>
                    <h1>Jobs picked for you</h1>
                    <p className="sub">Fresh openings from the companies you follow, ranked by how well they fit your resume.</p>
                </div>

                <div className="page-actions">
                    <button type="button" className="btn btn-glass" onClick={load} disabled={loading}>
                        {loading ? <span className="spinner sm" /> : <Icon name="refresh" />} Refresh
                    </button>
                </div>
            </header>

            <section className="stats" aria-label="Summary">
                <div className="stat glass"><span className="s-icon"><Icon name="briefcase" /></span><div><div className="v">{stats.found}</div><div className="l">Jobs found</div></div></div>
                <div className="stat glass good"><span className="s-icon"><Icon name="star" /></span><div><div className="v">{stats.strong}</div><div className="l">Strong matches</div></div></div>
                <div className="stat glass cyan"><span className="s-icon"><Icon name="bookmark" /></span><div><div className="v">{stats.tracked}</div><div className="l">Tracked</div></div></div>
                <div className="stat glass violet"><span className="s-icon"><Icon name="chat" /></span><div><div className="v">{stats.interviews}</div><div className="l">Interviews</div></div></div>
            </section>

            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

            {!loading && pending > 0 && (
                <div className="alert info">
                    <Icon name="sparkles" />
                    <span><b>{pending} {pending === 1 ? "job is" : "jobs are"} waiting for AI analysis.</b> Trace analyses a limited batch every hour (most relevant first), so match scores will fill in over time.</span>
                </div>
            )}

            <JobFilters filters={filters} onChange={setFilters} companies={companies} />

            <section className="job-grid" aria-busy={loading}>
                {loading && Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton skeleton-card" />)}

                {!loading && visible.map((job, i) => (
                    <JobCard key={job.id} job={job} index={i} application={appByJob.get(job.id)} onOpen={setSelected} onTrack={setTracking} />
                ))}

                {!loading && visible.length === 0 && (
                    <div className="empty glass">
                        <div className="empty-icon"><Icon name={filtering ? "search" : "building"} /></div>

                        {filtering ? (
                            <>
                                <h3>No jobs match those filters</h3>
                                <p>Try a broader search or lower the minimum match.</p>
                                <button type="button" className="btn btn-glass" onClick={() => setFilters(DEFAULT_FILTERS)}>Clear filters</button>
                            </>
                        ) : (
                            <>
                                <h3>No jobs yet</h3>
                                <p>Add the career pages of companies you'd like to work at. Trace checks them every hour and jobs will appear here.</p>
                                <button type="button" className="btn btn-primary" onClick={() => onNavigate("companies")}><Icon name="plus" /> Add companies</button>
                            </>
                        )}
                    </div>
                )}
            </section>

            {selected && (
                <JobDrawer
                    job={selected}
                    application={appByJob.get(selected.id)}
                    onClose={() => setSelected(null)}
                    onTrack={(job) => setTracking(job)}
                />
            )}

            {tracking && (
                <ApplicationTracker
                    job={tracking}
                    initialApplication={appByJob.get(tracking.id) ?? null}
                    onClose={handleTrackerClose}
                />
            )}
        </div>
    );
}
