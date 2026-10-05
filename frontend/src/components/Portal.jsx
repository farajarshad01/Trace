import { createPortal } from "react-dom";


/**
 * Render overlays directly under <body>. A `position: fixed` element is
 * positioned relative to the nearest ancestor with a transform, filter or
 * backdrop-filter - all of which the glass cards and animated pages use - so
 * overlays rendered in place get clipped to their parent instead of covering
 * the viewport.
 */
export default function Portal({ children }) {
    return createPortal(children, document.body);
}
