import { useEffect, useState } from "react";

import { initials } from "../utils/format";


/**
 * Company avatar. Shows the company's logo when we have one; otherwise (or if
 * the image fails to load - e.g. the site removed it) a solid-blue initial.
 */
export default function Avatar({ name, logo, size = "md", round = false, className = "" }) {
    const [failed, setFailed] = useState(false);

    useEffect(() => { setFailed(false); }, [logo]);

    const showLogo = Boolean(logo) && !failed;

    return (
        <span
            className={`avatar ${size === "sm" ? "sm" : size === "xs" ? "xs" : ""} ${round ? "round" : ""} ${showLogo ? "has-logo" : ""} ${className}`}
            aria-hidden="true"
        >
            {showLogo ? (
                <img
                    src={logo}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    referrerPolicy="no-referrer"
                    onError={() => setFailed(true)}
                />
            ) : initials(name).slice(0, 2)}
        </span>
    );
}
