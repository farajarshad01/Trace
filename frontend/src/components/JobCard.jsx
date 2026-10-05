import Avatar from "./Avatar";
import Icon from "./Icon";
import ScoreRing from "./ScoreRing";
import { statusClass, timeAgo } from "../utils/format";


export default function JobCard({ job, application, index = 0, onOpen, onTrack }) {
    const skills = (job.required_skills || []).slice(0, 4);
    const matched = new Set((job.matched_skills || []).map((s) => s.toLowerCase()));
    const scored = job.match_score !== null && job.match_score !== undefined;

    const stop = (fn) => (event) => {
        event.stopPropagation();
        fn?.();
    };

    return (
        <article
            className={`job-card glass interactive ${application ? "tracked" : ""}`}
            style={{ "--i": Math.min(index, 12) }}
            role="button"
            tabIndex={0}
            aria-label={`${job.title} at ${job.company_name}. Open details`}
            onClick={() => onOpen(job)}
            onKeyDown={(e) => {
                if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onOpen(job);
                }
            }}
        >
            <div className="jc-top">
                <Avatar name={job.company_name} />

                <div className="jc-title">
                    <div className="jc-company">{job.company_name}</div>
                    <h3>{job.title}</h3>
                </div>

                {scored
                    ? <ScoreRing value={job.match_score} size={54} />
                    : <span className="unscored">Not<br />scored</span>}
            </div>

            <div className="chips">
                {job.location && <span className="chip neutral"><Icon name="pin" />{job.location}</span>}
                {job.employment_type && <span className="chip neutral"><Icon name="briefcase" />{job.employment_type}</span>}
                <span className="chip neutral"><Icon name="clock" />{timeAgo(job.first_seen_at)}</span>
            </div>

            {job.role_summary
                ? <p className="jc-summary">{job.role_summary}</p>
                : <p className="jc-summary pending"><Icon name="sparkles" />Waiting for AI analysis…</p>}

            {skills.length > 0 && (
                <div className="chips">
                    {skills.map((skill) => (
                        <span key={skill} className={`chip ${matched.has(skill.toLowerCase()) ? "good" : "neutral"}`}>
                            {matched.has(skill.toLowerCase()) && <Icon name="check" strokeWidth={3} />}
                            {skill}
                        </span>
                    ))}
                </div>
            )}

            <div className="jc-foot">
                <a
                    className="btn btn-glass btn-sm"
                    href={job.original_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                >
                    Apply <Icon name="external" />
                </a>

                {application ? (
                    <button type="button" className={`btn btn-sm btn-status ${statusClass(application.status)}`} onClick={stop(() => onTrack(job))}>
                        <span className="dot" />{application.status}
                    </button>
                ) : (
                    <button type="button" className="btn btn-primary btn-sm" onClick={stop(() => onTrack(job))}>
                        <Icon name="bookmark" /> Track
                    </button>
                )}
            </div>
        </article>
    );
}
