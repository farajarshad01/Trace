import { useEffect } from "react";


/** Close an overlay on Escape and stop the page behind it from scrolling. */
export function useOverlay(onClose) {
    useEffect(() => {
        const onKey = (event) => {
            if (event.key === "Escape") onClose();
        };

        const previous = document.body.style.overflow;

        document.addEventListener("keydown", onKey);
        document.body.style.overflow = "hidden";

        return () => {
            document.removeEventListener("keydown", onKey);
            document.body.style.overflow = previous;
        };
    }, [onClose]);
}
