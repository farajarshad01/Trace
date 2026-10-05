import { useRef } from "react";

import Icon from "./Icon";


const SNIPPETS = [
    { label: "Interview note", text: "Interview — " },
    { label: "To-do", text: "☐ " },
    { label: "Contact", text: "Contact: " },
];


/**
 * Controlled notes field for logging interview thoughts and tasks.
 * Quick-insert chips add a prefix on a new line at the cursor;
 * Ctrl/Cmd + Enter triggers `onSubmit` if provided.
 */
export default function NoteEditor({
    value,
    onChange,
    onSubmit,
    maxLength = 5000,
    saved = false,
    autoFocus = false,
    rows = 6,
}) {
    const ref = useRef(null);

    function insert(snippet) {
        const el = ref.current;
        const start = el ? el.selectionStart : value.length;
        const before = value.slice(0, start);
        const after = value.slice(el ? el.selectionEnd : value.length);
        const lead = before && !before.endsWith("\n") ? "\n" : "";
        const next = `${before}${lead}${snippet}${after}`;

        onChange(next.slice(0, maxLength));

        requestAnimationFrame(() => {
            if (!el) return;

            const caret = (before + lead + snippet).length;

            el.focus();
            el.setSelectionRange(caret, caret);
        });
    }

    return (
        <div className="note-editor">
            <div className="note-tools">
                {SNIPPETS.map((s) => (
                    <button key={s.label} type="button" className="chip neutral" onClick={() => insert(s.text)}>
                        <Icon name="plus" /> {s.label}
                    </button>
                ))}
            </div>

            <textarea
                ref={ref}
                className="field"
                rows={rows}
                value={value}
                maxLength={maxLength}
                autoFocus={autoFocus}
                placeholder="Interview thoughts, follow-ups, recruiter details, tasks…"
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={(e) => {
                    if (onSubmit && e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        onSubmit();
                    }
                }}
            />

            <div className="note-foot">
                <span>{value.length.toLocaleString()} / {maxLength.toLocaleString()}</span>
                {saved ? <span className="saved"><Icon name="check" strokeWidth={3} /> Saved</span> : onSubmit && <span>Ctrl + Enter to save</span>}
            </div>
        </div>
    );
}
