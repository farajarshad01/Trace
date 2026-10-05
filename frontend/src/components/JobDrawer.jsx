import { useEffect, useState } from "react";

import Avatar from "./Avatar";
import Icon from "./Icon";
import Portal from "./Portal";
import MatchReport from "./MatchReport";
import ScoreRing from "./ScoreRing";
import { getJob } from "../services/api";
import { formatDate, statusClass } from "../utils/format";
import { useOverlay } from "../utils/hooks";


function verdict(score) {
    if (score >= 80) return "Strong match — your profile lines up well.";
    if (score >= 60) return "Good match — worth a closer look.";
    if (score >= 40) return "Partial match — some gaps to close.";

    return "Low match for your current profile.";
}


export default function JobDrawer({ job, application, onClose, onTrack }) {
    const [detail, setDetail] = useState(null);
    const [loading, setLoading] = useState(true);

    useOverlay(onClose);

    useEffect(() => {
        let cancelled = false;

        setDetail(null);
        setLoading(true);

        getJob(job.id)
            .then((data) => { if (!cancelled) setDetail(data); })
            .catch(() => { /* list data is still shown */ })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, [job.id]);

    const j = { ...job, ...(detail || {}) };
    const scored = j.match_score !== null && j.match_score !== undefined;

    return (
        <Portal>
            <div className="overlay" onClick={onClose} />

            <aside className="drawer glass strong" role="dialog" aria-modal="true" aria-label={`${j.title} at ${j.company_name}`}>
                <div className="drawer-head">
                    <Avatar name={j.company_name} />

                    <div className="drawer-title">
                        <div className="jc-company">{j.company_name}</div>
                        <h2>{j.title}</h2>
                    </div>

                    <button type="button" className="close-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
                </div>

                <div className="drawer-body">
                    <div className="chips">
                        {j.location && <span className="chip neutral"><Icon name="pin" />{j.location}</span>}
                        {j.employment_type && <span className="chip neutral"><Icon name="briefcase" />{j.employment_type}</span>}
                        <span className="chip neutral"><Icon name="calendar" />First seen {formatDate(j.first_seen_at)}</span>
                        {application && <span className={`status-pill ${statusClass(application.status)}`}><span className="dot" />{application.status}</span>}
                    </div>

                    {scored ? (
                        <section>
                            <div className="score-hero">
                                <ScoreRing value={j.match_score} size={84} stroke={7} label />
                                <div className="sh-text">
                                    <b>{verdict(j.match_score)}</b>
                                    <p>Compared against your resume and target roles.</p>
                                </div>
                            </div>

                            <div style={{ marginTop: 18 }}><MatchReport job={j} /></div>
                        </section>
                    ) : (
                        <div className="alert info">
                            <Icon name="sparkles" />
                            <span>{j.analyzed
                                ? <>There wasn't enough detail in this posting to score it.</>
                                : <><b>Not scored yet.</b> Trace analyses a limited batch of new jobs each hour, so scores fill in over time.</>}</span>
                        </div>
                    )}

                    {j.role_summary && (
                        <section>
                            <div className="section-title">About the role</div>
                            <p className="prose">{j.role_summary}</p>
                        </section>
                    )}

                    {(j.matched_skills?.length > 0 || j.missing_skills?.length > 0) && (
                        <section>
                            {j.matched_skills?.length > 0 && (
                                <>
                                    <div className="section-title">Skills you have</div>
                                    <div className="chips">{j.matched_skills.map((s) => <span key={s} className="chip good"><Icon name="check" strokeWidth={3} />{s}</span>)}</div>
                                </>
                            )}

                            {j.missing_skills?.length > 0 && (
                                <div style={{ marginTop: j.matched_skills?.length ? 18 : 0 }}>
                                    <div className="section-title">Skills to build</div>
                                    <div className="chips">{j.missing_skills.map((s) => <span key={s} className="chip warn">{s}</span>)}</div>
                                </div>
                            )}
                        </section>
                    )}

                    {(j.preferred_skills?.length > 0) && (
                        <section>
                            <div className="section-title">Nice to have</div>
                            <div className="chips">{j.preferred_skills.map((s) => <span key={s} className="chip neutral">{s}</span>)}</div>
                        </section>
                    )}

                    {(j.experience_requirements || j.education_requirements) && (
                        <section>
                            <div className="section-title">Requirements</div>
                            <dl className="kv">
                                {j.experience_requirements && <div><dt>Experience</dt><dd>{j.experience_requirements}</dd></div>}
                                {j.education_requirements && <div><dt>Education</dt><dd>{j.education_requirements}</dd></div>}
                            </dl>
                        </section>
                    )}

                    <section>
                        <div className="section-title">Full description</div>

                        {loading && <div className="skeleton" style={{ height: 120 }} />}
                        {!loading && j.description && <div className="desc-box"><p className="prose">{j.description}</p></div>}
                        {!loading && !j.description && <p className="prose">No description was captured for this posting. Open the original listing for details.</p>}
                    </section>
                </div>

                <div className="drawer-foot">
                    <a className="btn btn-glass" href={j.original_url} target="_blank" rel="noopener noreferrer">Apply <Icon name="external" /></a>
                    <button type="button" className="btn btn-primary" onClick={() => onTrack(job)}>
                        <Icon name="bookmark" /> {application ? "Update tracking" : "Track this job"}
                    </button>
                </div>
            </aside>
        </Portal>
    );
}
