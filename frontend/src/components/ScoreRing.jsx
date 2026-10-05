import { useEffect, useState } from "react";

import { scoreTone } from "../utils/format";


export default function ScoreRing({ value, size = 56, stroke = 5, label = false }) {
    const [shown, setShown] = useState(0);

    useEffect(() => {
        const frame = requestAnimationFrame(() => setShown(value ?? 0));

        return () => cancelAnimationFrame(frame);
    }, [value]);

    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - Math.min(Math.max(shown, 0), 100) / 100);
    const tone = scoreTone(value ?? 0);

    return (
        <div
            className={`ring score-${tone}`}
            style={{ width: size, height: size }}
            role="img"
            aria-label={`${Math.round(value)} percent match`}
        >
            <svg width={size} height={size}>
                <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
                <circle
                    className="ring-value"
                    cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke}
                    stroke="var(--score)"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                />
            </svg>

            <div className="ring-label" style={{ fontSize: size * 0.32 }}>
                <span>{Math.round(value)}<span style={{ fontSize: "0.55em" }}>%</span></span>
                {label && <small>match</small>}
            </div>
        </div>
    );
}
