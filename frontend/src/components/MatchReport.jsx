import { scoreTone } from "../utils/format";


const ROWS = [
    ["skill_match", "Skills"],
    ["role_match", "Role fit"],
    ["experience_match", "Experience"],
    ["education_match", "Education"],
];


/** Per-component bars. Components the backend could not score are hidden. */
export default function MatchReport({ job }) {
    const rows = ROWS.filter(([key]) => job[key] !== null && job[key] !== undefined);

    return (
        <div>
            {rows.map(([key, label]) => (
                <div className={`bar-row score-${scoreTone(job[key])}`} key={key}>
                    <span className="name">{label}</span>
                    <div className="bar" role="progressbar" aria-valuenow={Math.round(job[key])} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
                        <i style={{ width: `${Math.round(job[key])}%` }} />
                    </div>
                    <span className="pct">{Math.round(job[key])}%</span>
                </div>
            ))}
        </div>
    );
}
