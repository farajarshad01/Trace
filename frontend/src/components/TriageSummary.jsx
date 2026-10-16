import Icon from "./Icon";


/** Left panel: how far through the inbox you are, and where else things went. */
export default function TriageSummary({
    reviewed, total, pipeline, hidden, skipped, strongLeft, view, roles, pending,
    refreshing, onRefresh, onToggleHidden, onPipeline, onEditRoles,
}) {
    return (
        <aside className="tri-sum glass strong" aria-label="Triage summary">
            <div className="tri-sum-head">
                <div>
                    <div className="eyebrow">Triage</div>
                    <h1>Inbox for jobs</h1>
                    <p className="tri-sub">Decide on new roles in under a minute.</p>
                </div>

                <button type="button" className="btn btn-glass btn-icon btn-sm" onClick={onRefresh} disabled={refreshing} aria-label="Refresh jobs" title="Refresh">
                    {refreshing ? <span className="spinner sm" /> : <Icon name="refresh" />}
                </button>
            </div>

            <div className="tri-count">
                <div className="tri-big">{reviewed}<span> / {total}</span></div>
                <div className="tri-sub">reviewed this session</div>
            </div>

            <div className="tri-stats">
                <button type="button" className="tri-stat" onClick={onPipeline}>
                    <span className="ic"><Icon name="bookmark" /></span><span>In your pipeline</span><b>{pipeline}</b>
                </button>

                <button type="button" className={`tri-stat ${view === "hidden" ? "on" : ""}`} onClick={onToggleHidden} aria-pressed={view === "hidden"}>
                    <span className="ic"><Icon name="eyeoff" /></span><span>{view === "hidden" ? "Back to inbox" : "Hidden"}</span><b>{view === "hidden" ? "" : hidden}</b>
                </button>

                <div className="tri-stat static">
                    <span className="ic"><Icon name="arrow" /></span><span>Skipped for now</span><b>{skipped}</b>
                </div>

                <div className="tri-stat static">
                    <span className="ic"><Icon name="star" /></span><span>Strong matches left</span><b>{strongLeft}</b>
                </div>
            </div>

            <div className="tri-notes">
                {pending > 0 && (
                    <div className="tri-note">
                        <div className="tri-note-title"><Icon name="sparkles" />{pending} {pending === 1 ? "job" : "jobs"} awaiting AI</div>
                        <p>Scores appear over the next few hourly runs, most relevant first.</p>
                    </div>
                )}

                <div className="tri-note">
                    <div className="tri-note-title"><Icon name="target" />Looking for</div>

                    {roles.length > 0 ? (
                        <div className="chips">
                            {roles.slice(0, 4).map((r) => <span className="chip" key={r.id}>{r.role_title}</span>)}
                            {roles.length > 4 && <span className="chip neutral">+{roles.length - 4}</span>}
                        </div>
                    ) : <p>No target roles yet, so every job is shown.</p>}

                    <button type="button" className="tri-link" onClick={onEditRoles}>Edit target roles <Icon name="arrow" /></button>
                </div>
            </div>
        </aside>
    );
}
