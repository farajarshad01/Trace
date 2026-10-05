import { useState } from "react";

import Icon from "./Icon";


/** Add / remove target roles. Used in onboarding and on the Resume page. */
export default function RoleEditor({ roles, onAdd, onRemove, suggestions = [], disabled = false }) {
    const [value, setValue] = useState("");
    const [busy, setBusy] = useState(false);

    const have = new Set(roles.map((r) => r.role_title.toLowerCase()));
    const open = suggestions.filter((s) => !have.has(s.toLowerCase())).slice(0, 8);

    async function submit(title) {
        const clean = title.trim();

        if (!clean || have.has(clean.toLowerCase()) || busy) return;

        setBusy(true);

        try {
            await onAdd(clean);
            setValue("");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div>
            {roles.length > 0 ? (
                <div className="chips">
                    {roles.map((role) => (
                        <span className="chip lg" key={role.id}>
                            {role.role_title}
                            <button type="button" className="chip-x" aria-label={`Remove ${role.role_title}`} onClick={() => onRemove(role)} disabled={disabled}>
                                <Icon name="x" strokeWidth={3} />
                            </button>
                        </span>
                    ))}
                </div>
            ) : (
                <p className="hint" style={{ marginBottom: 0 }}>No target roles yet — add at least one so Trace can rank jobs for you.</p>
            )}

            <form className="role-add" onSubmit={(e) => { e.preventDefault(); submit(value); }}>
                <input
                    className="field"
                    value={value}
                    maxLength={120}
                    placeholder="Add a role…"
                    onChange={(e) => setValue(e.target.value)}
                    aria-label="Add a target role"
                    disabled={disabled}
                />
                <button type="submit" className="btn btn-primary" disabled={!value.trim() || busy || disabled}>
                    <Icon name="plus" /> Add
                </button>
            </form>

            {open.length > 0 && (
                <div style={{ marginTop: 16 }}>
                    <div className="section-title"><Icon name="sparkles" size={14} /> Suggested from your resume</div>

                    <div className="chips">
                        {open.map((s) => (
                            <button key={s} type="button" className="chip neutral" onClick={() => submit(s)} disabled={disabled || busy}>
                                <Icon name="plus" /> {s}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
