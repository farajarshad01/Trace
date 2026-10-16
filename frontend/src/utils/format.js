export const STATUSES = ["Saved", "Applied", "Interview", "Offer", "Rejected", "Withdrawn"];

export const statusClass = (status) => `s-${String(status || "saved").toLowerCase()}`;


export function timeAgo(value) {
    if (!value) return "";

    const then = new Date(value).getTime();

    if (Number.isNaN(then)) return "";

    const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));

    if (seconds < 60) return "just now";

    const units = [
        [60, "minute"], [3600, "hour"], [86400, "day"],
        [604800, "week"], [2629800, "month"], [31557600, "year"],
    ];

    let chosen = units[0];

    for (const unit of units) {
        if (seconds >= unit[0]) chosen = unit;
    }

    const amount = Math.floor(seconds / chosen[0]);

    return `${amount} ${chosen[1]}${amount === 1 ? "" : "s"} ago`;
}


export function formatDate(value) {
    if (!value) return "";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}


export function initials(name = "") {
    const parts = String(name).trim().split(/\s+/).filter(Boolean);

    if (!parts.length) return "?";

    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}


export function hostname(url) {
    try {
        return new URL(url).hostname.replace(/^www\./, "");
    } catch {
        return url;
    }
}


export function normalizeUrl(input) {
    const trimmed = String(input || "").trim();

    if (!trimmed) return "";

    return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}


/** Resume entries can be strings (older profiles) or objects. */
export function entryParts(entry, kind) {
    if (typeof entry === "string") return { title: entry, sub: "", when: "", text: "" };

    const e = entry || {};

    if (kind === "education") {
        return {
            title: e.degree || e.title || e.name || "Education",
            sub: e.institution || e.school || e.university || "",
            when: e.year || e.duration || e.dates || "",
            text: "",
        };
    }

    if (kind === "project") {
        return {
            title: e.name || e.title || "Project",
            sub: Array.isArray(e.technologies) ? e.technologies.join(" · ") : "",
            when: "",
            text: e.summary || e.description || "",
        };
    }

    return {
        title: e.title || e.position || e.role || "Role",
        sub: e.company || e.organization || "",
        when: e.duration || e.dates || e.period || "",
        text: e.summary || e.description || "",
    };
}
