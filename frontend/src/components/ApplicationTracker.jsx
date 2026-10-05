import { useEffect, useState } from "react";

import Avatar from "./Avatar";
import Icon from "./Icon";
import Portal from "./Portal";
import NoteEditor from "./NoteEditor";
import { useToast } from "./Toast";
import {
    deleteApplication,
    getApplication,
    updateApplication,
} from "../services/api";
import { STATUSES, statusClass } from "../utils/format";
import { useOverlay } from "../utils/hooks";


const STATUS_ICON = {
    Saved: "bookmark", Applied: "mail", Interview: "chat",
    Offer: "trophy", Rejected: "x", Withdrawn: "ban",
};


/**
 * Modal for tracking a job: pick a status and keep notes.
 * `onClose(change)` receives "saved" | "removed" | false.
 */
export default function ApplicationTracker({ job, initialApplication = null, onClose }) {
    const toast = useToast();

    const [status, setStatus] = useState(initialApplication?.status || "Saved");
    const [notes, setNotes] = useState(initialApplication?.notes || "");
    const [existing, setExisting] = useState(Boolean(initialApplication));
    const [loading, setLoading] = useState(!initialApplication);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const close = () => onClose(false);

    useOverlay(close);

    useEffect(() => {
        if (initialApplication) return undefined;

        let cancelled = false;

        getApplication(job.id)
            .then((app) => {
                if (cancelled || !app) return;

                setStatus(app.status);
                setNotes(app.notes || "");
                setExisting(true);
            })
            .catch((err) => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, [job.id, initialApplication]);

    async function save() {
        if (saving) return;

        setSaving(true);
        setError("");

        try {
            await updateApplication(job.id, status, notes);
            toast.success(existing ? "Application updated" : "Added to your tracker");
            onClose("saved");
        } catch (err) {
            setError(err.message);
            setSaving(false);
        }
    }

    async function remove() {
        setSaving(true);

        try {
            await deleteApplication(job.id);
            toast.success("Removed from your tracker");
            onClose("removed");
        } catch (err) {
            setError(err.message);
            setSaving(false);
        }
    }

    return (
        <Portal>
            <div className="overlay" onClick={close} />

            <div className="modal-wrap" onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
                <div className="modal glass strong" role="dialog" aria-modal="true" aria-label="Track application">
                    <div className="modal-head">
                        <Avatar name={job.company_name} size="sm" />

                        <div style={{ minWidth: 0 }}>
                            <div className="jc-company">{job.company_name}</div>
                            <h3>{job.title}</h3>
                        </div>

                        <button type="button" className="close-btn" onClick={close} aria-label="Close"><Icon name="x" /></button>
                    </div>

                    {loading ? (
                        <div style={{ display: "grid", placeItems: "center", padding: 48 }}><div className="spinner" /></div>
                    ) : (
                        <>
                            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

                            <div className="label">Status</div>

                            <div className="status-grid" role="radiogroup" aria-label="Application status">
                                {STATUSES.map((s) => (
                                    <button
                                        key={s}
                                        type="button"
                                        role="radio"
                                        aria-checked={status === s}
                                        className={`status-opt ${statusClass(s)} ${status === s ? "on" : ""}`}
                                        onClick={() => setStatus(s)}
                                    >
                                        <Icon name={STATUS_ICON[s]} size={16} /> {s}
                                    </button>
                                ))}
                            </div>

                            <div className="label" style={{ marginTop: 22 }}>Notes</div>
                            <NoteEditor value={notes} onChange={setNotes} onSubmit={save} />

                            <div style={{ display: "flex", gap: 10, marginTop: 22, alignItems: "center" }}>
                                {existing && (
                                    <button type="button" className="btn btn-danger btn-sm" onClick={remove} disabled={saving}>
                                        <Icon name="trash" /> Remove
                                    </button>
                                )}

                                <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
                                    <button type="button" className="btn btn-ghost" onClick={close} disabled={saving}>Cancel</button>
                                    <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
                                        {saving ? <span className="spinner sm" /> : <Icon name="check" strokeWidth={3} />}
                                        {saving ? "Saving…" : "Save"}
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </Portal>
    );
}
