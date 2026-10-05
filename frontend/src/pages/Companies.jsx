import { useEffect, useState } from "react";

import Avatar from "../components/Avatar";
import Icon from "../components/Icon";
import { useToast } from "../components/Toast";
import { createSource, deleteSource, getSources } from "../services/api";
import { hostname, normalizeUrl, timeAgo } from "../utils/format";


const PLATFORMS = {
    greenhouse: { label: "Greenhouse", tone: "good" },
    lever: { label: "Lever", tone: "" },
    workday: { label: "Workday", tone: "warn" },
    generic: { label: "Careers page", tone: "neutral" },
};


export default function Companies() {
    const toast = useToast();

    const [sources, setSources] = useState([]);
    const [loading, setLoading] = useState(true);
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState("");
    const [name, setName] = useState("");
    const [url, setUrl] = useState("");
    const [confirming, setConfirming] = useState(null);

    useEffect(() => {
        let cancelled = false;

        getSources()
            .then((list) => { if (!cancelled) setSources(list || []); })
            .catch((err) => { if (!cancelled) setError(err.message); })
            .finally(() => { if (!cancelled) setLoading(false); });

        return () => { cancelled = true; };
    }, []);

    async function handleAdd(event) {
        event.preventDefault();

        const careerUrl = normalizeUrl(url);

        try {
            new URL(careerUrl);
        } catch {
            setError("That doesn't look like a valid web address.");
            return;
        }

        setAdding(true);
        setError("");

        try {
            const source = await createSource(name.trim(), careerUrl);

            setSources((list) => [source, ...list.filter((s) => s.id !== source.id)]);
            setName("");
            setUrl("");
            toast.success(`${source.company_name} added — Trace will check it on the next hourly run`);
        } catch (err) {
            setError(err.message);
        } finally {
            setAdding(false);
        }
    }

    async function handleRemove(source) {
        try {
            await deleteSource(source.id);
            setSources((list) => list.filter((s) => s.id !== source.id));
            toast.success(`${source.company_name} removed`);
        } catch (err) {
            setError(err.message);
        } finally {
            setConfirming(null);
        }
    }

    return (
        <div className="page">
            <header className="page-head">
                <div>
                    <div className="eyebrow">Companies</div>
                    <h1>Where should Trace look?</h1>
                    <p className="sub">Add career pages you want to monitor. Trace checks every source once an hour and analyses new openings for you.</p>
                </div>
            </header>

            <section className="add-card glass strong">
                <form className="add-form" onSubmit={handleAdd}>
                    <input className="field" placeholder="Company name" value={name} maxLength={255} required onChange={(e) => setName(e.target.value)} aria-label="Company name" />
                    <input className="field" placeholder="Careers page URL, e.g. boards.greenhouse.io/acme" value={url} required onChange={(e) => setUrl(e.target.value)} aria-label="Careers page URL" inputMode="url" />

                    <button type="submit" className="btn btn-primary" disabled={adding || !name.trim() || !url.trim()}>
                        {adding ? <span className="spinner sm" /> : <Icon name="plus" />} Add company
                    </button>
                </form>

                <div className="platforms">
                    <span>Works best with</span>
                    <span className="chip good">Greenhouse</span>
                    <span className="chip">Lever</span>
                    <span className="chip warn">Workday</span>
                    <span className="chip neutral">Other careers pages</span>
                </div>
            </section>

            {error && <div className="alert error"><Icon name="alert" /><span>{error}</span></div>}

            <section className="source-grid" aria-busy={loading}>
                {loading && Array.from({ length: 3 }, (_, i) => <div key={i} className="skeleton" style={{ height: 104, borderRadius: 22 }} />)}

                {!loading && sources.map((source, i) => {
                    const platform = PLATFORMS[source.platform] || PLATFORMS.generic;

                    return (
                        <article className="source-card glass" key={source.id} style={{ "--i": i }}>
                            <Avatar name={source.company_name} />

                            <div className="sc-main">
                                <h3>{source.company_name}</h3>
                                <a className="url" href={source.career_url} target="_blank" rel="noopener noreferrer" title={source.career_url}>{hostname(source.career_url)}</a>

                                <div className="meta">
                                    <span className={`chip ${platform.tone}`}>{platform.label}</span>
                                    <span className="chip neutral"><Icon name="clock" />{source.last_checked_at ? `Checked ${timeAgo(source.last_checked_at)}` : "Not checked yet"}</span>
                                </div>
                            </div>

                            {confirming === source.id ? (
                                <div className="confirm-row">
                                    <button type="button" className="btn btn-danger btn-sm" onClick={() => handleRemove(source)}>Remove</button>
                                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirming(null)}>Cancel</button>
                                </div>
                            ) : (
                                <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setConfirming(source.id)} aria-label={`Remove ${source.company_name}`} title="Remove">
                                    <Icon name="trash" />
                                </button>
                            )}
                        </article>
                    );
                })}

                {!loading && sources.length === 0 && (
                    <div className="empty glass">
                        <div className="empty-icon"><Icon name="building" /></div>
                        <h3>No companies yet</h3>
                        <p>Paste a careers page above to start monitoring it. Greenhouse and Lever boards give the richest results.</p>
                    </div>
                )}
            </section>
        </div>
    );
}
