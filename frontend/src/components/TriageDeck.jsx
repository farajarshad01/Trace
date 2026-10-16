import Avatar from "./Avatar";
import Icon from "./Icon";
import MatchReport from "./MatchReport";
import ScoreRing from "./ScoreRing";
import { timeAgo } from "../utils/format";


function ActionButton({ icon, label, kbd, onClick, main = false, disabled = false }) {
    return (
        <div className="tri-act">
            <button
                type="button"
                className={`tri-circle ${main ? "main" : ""}`}
                onClick={onClick}
                disabled={disabled}
                aria-label={`${label} (${kbd})`}
            >
                <Icon name={icon} />
            </button>

            <span className="tri-act-label">{label}</span>
            <span className="kbd" aria-hidden="true">{kbd}</span>
        </div>
    );
}


function Hint({ keys, label, onClick, disabled }) {
    return (
        <button type="button" className="tri-hint" onClick={onClick} disabled={disabled}>
            {keys.map((k) => <span className="kbd" key={k} aria-hidden="true">{k}</span>)}
            {label}
        </button>
    );
}


/**
 * One job at a time, with two cards peeking out underneath.
 * mode "queue":  Not relevant / Track / Apply.
 * mode "hidden": Restore / Apply (reviewing jobs you hid earlier).
 */
export default function TriageDeck({
    job, mode = "queue", peeks = 0, canSkip = true, canGoBack = false, canGoNext = false, canUndo = false,
    onHide, onTrack, onApply, onSkip, onRestore, onDetails, onUndo, onPrev, onNext,
}) {
    const scored = job.match_score !== null && job.match_score !== undefined;
    const have = job.matched_skills || [];
    const build = job.missing_skills || [];
    const hasBars = ["skill_match", "role_match", "experience_match", "education_match"].some((k) => job[k] !== null && job[k] !== undefined);

    return (
        <div className="tri-stage-inner">
            <div className="tri-deck">
                {peeks > 1 && <div className="tri-peek p2" aria-hidden="true" />}
                {peeks > 0 && <div className="tri-peek p1" aria-hidden="true" />}

                <article key={job.id} className="tri-card" aria-label={`${job.title} at ${job.company_name}`}>
                    <header className="tri-card-head">
                        <Avatar name={job.company_name} logo={job.company_logo_url} className="tri-avatar" />

                        <div className="tri-card-title">
                            <div className="jc-company">{job.company_name}</div>
                            <h2>{job.title}</h2>
                        </div>

                        {scored
                            ? <ScoreRing value={job.match_score} size={104} stroke={9} label />
                            : <span className="unscored">Not<br />scored</span>}
                    </header>

                    <div className="chips tri-chips">
                        {job.location && <span className="chip neutral"><Icon name="pin" />{job.location}</span>}
                        {job.employment_type && <span className="chip neutral"><Icon name="briefcase" />{job.employment_type}</span>}
                        <span className="chip neutral"><Icon name="clock" />{timeAgo(job.first_seen_at)}</span>
                    </div>

                    {job.role_summary
                        ? <p className="tri-summary">{job.role_summary}</p>
                        : <p className="tri-summary pending"><Icon name="sparkles" />Waiting for AI analysis. Open the full description to judge it yourself.</p>}

                    {have.length > 0 && (
                        <section className="tri-block">
                            <div className="label">Why it matches</div>
                            <div className="chips">{have.map((s) => <span className="chip" key={s}><Icon name="check" strokeWidth={3} />{s}</span>)}</div>
                        </section>
                    )}

                    {build.length > 0 && (
                        <section className="tri-block">
                            <div className="label">To build</div>
                            <div className="chips">{build.map((s) => <span className="chip neutral" key={s}>{s}</span>)}</div>
                        </section>
                    )}

                    {!scored && (job.required_skills || []).length > 0 && (
                        <section className="tri-block">
                            <div className="label">Asks for</div>
                            <div className="chips">{job.required_skills.slice(0, 8).map((s) => <span className="chip neutral" key={s}>{s}</span>)}</div>
                        </section>
                    )}

                    {hasBars && <div className="tri-bars"><MatchReport job={job} /></div>}

                </article>
            </div>

            <div className="tri-actions">
                {mode === "queue" ? (
                    <>
                        <ActionButton icon="eyeoff" label="Not relevant" kbd="H" onClick={onHide} />
                        <ActionButton icon="bookmark" label="Track" kbd="T" onClick={onTrack} main />
                        <ActionButton icon="external" label="Apply" kbd="A" onClick={onApply} />
                    </>
                ) : (
                    <>
                        <ActionButton icon="undo" label="Restore" kbd="R" onClick={onRestore} main />
                        <ActionButton icon="external" label="Apply" kbd="A" onClick={onApply} />
                    </>
                )}
            </div>

            <div className="tri-hints">
                {mode === "queue" && <Hint keys={["S"]} label="Skip for now" onClick={onSkip} disabled={!canSkip} />}
                {mode === "queue" && <Hint keys={["Z"]} label="Undo" onClick={onUndo} disabled={!canUndo} />}
                <Hint keys={["←"]} label="Previous" onClick={onPrev} disabled={!canGoBack} />
                <Hint keys={["→"]} label="Next" onClick={onNext} disabled={!canGoNext} />
                <Hint keys={["D"]} label="Full description" onClick={onDetails} />
            </div>
        </div>
    );
}
