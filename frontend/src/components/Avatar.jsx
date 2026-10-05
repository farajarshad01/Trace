import { avatarGradient, initials } from "../utils/format";


export default function Avatar({ name, size = "md", round = false, className = "" }) {
    return (
        <span
            className={`avatar ${size === "sm" ? "sm" : ""} ${round ? "round" : ""} ${className}`}
            style={{ background: avatarGradient(name) }}
            aria-hidden="true"
        >
            {initials(name).slice(0, 2)}
        </span>
    );
}
