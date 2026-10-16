import { useEffect, useRef } from "react";

import Avatar from "./Avatar";
import Icon from "./Icon";
import ScoreRing from "./ScoreRing";


/** The "Up next" list: jump to any job, and narrow the queue with filters. */
export default function TriageQueue({ jobs, currentId, view, filters, onFilters, companies, filtering, onClear, onSelect }) {
    const rows = useRef(new Map());
    const list = useRef(null);

    // Keep the current job visible inside the list as you move through the queue.
    // This scrolls ONLY the list. scrollIntoView() would scroll every ancestor too,
    // including the window, which on a phone (queue below the deck) threw the page
    // down to the queue on load.
    useEffect(() => {
        const box = list.current;
        const row = rows.current.get(currentId);

        if (!box || !row) return;

        const top = row.offsetTop;
        const bottom = top + row.offsetHeight;

        if (top < box.scrollTop) box.scrollTop = Math.max(top - 8, 0);
        else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 8;
    }, [currentId]);

    const set = (key) => (event) => onFilters({ ...filters, [key]: event.target.value });

    // After choosing from a dropdown, hand the keyboard back to the shortcuts.
    const pick = (key) => (event) => {
        set(key)(event);
        event.target.blur();
    };

    return (
        <aside className="tri-queue glass strong" aria-label={view === "hidden" ? "Hidden jobs" : "Up next"}>
            <div className="tri-queue-head">
                <div className="label">{view === "hidden" ? "Hidden jobs" : "Up next"}</div>
                <span className="chip">{jobs.length}</span>
            </div>

            <div className="tri-filters">
                <div className="input-wrap">
                    <Icon name="search" className="icon" />
                    <input className="field" type="search" placeholder="Search title, company, skill…" value={filters.query} onChange={set("query")} aria-label="Search jobs" />
                </div>

                <div className="tri-filter-row">
                    <select className="field" value={filters.company} onChange={pick("company")} aria-label="Company">
                        <option value="all">All companies</option>
                        {companies.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>

                    <select className="field" value={filters.minMatch} onChange={pick("minMatch")} aria-label="Minimum match">
                        <option value="0">Any match</option>
                        <option value="50">50%+</option>
                        <option value="70">70%+</option>
                        <option value="80">80%+</option>
                        <option value="90">90%+</option>
                    </select>
                </div>
            </div>

            <div className="tri-list" ref={list}>
                {jobs.map((job) => (
                    <button
                        key={job.id}
                        type="button"
                        ref={(node) => { if (node) rows.current.set(job.id, node); else rows.current.delete(job.id); }}
                        className={`tri-row ${job.id === currentId ? "on" : ""}`}
                        aria-current={job.id === currentId ? "true" : undefined}
                        onClick={() => onSelect(job.id)}
                    >
                        <Avatar name={job.company_name} logo={job.company_logo_url} size="sm" />

                        <span className="tri-row-text">
                            <span className="tri-row-title">{job.title}</span>
                            <span className="tri-row-meta">{job.company_name}{job.location ? ` · ${job.location}` : ""}</span>
                        </span>

                        {job.match_score !== null && job.match_score !== undefined && <ScoreRing value={job.match_score} size={38} stroke={4} />}
                    </button>
                ))}

                {jobs.length === 0 && (
                    <p className="tri-list-empty">
                        {filtering ? "No jobs match these filters." : "Nothing here."}
                        {filtering && <button type="button" className="btn btn-glass btn-sm" onClick={onClear}>Clear filters</button>}
                    </p>
                )}
            </div>
        </aside>
    );
}
