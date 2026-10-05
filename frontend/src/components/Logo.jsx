/**
 * Transparent logo. Two variants are rendered and CSS swaps them with the
 * theme: navy wordmark on light, white wordmark on dark.
 */
export default function Logo({ variant = "full", height = 28, className = "" }) {
    const suffix = variant === "mark" ? "-mark" : "";
    const ratio = variant === "mark" ? 258 / 247 : 938 / 247;
    const width = Math.round(height * ratio);

    return (
        <span className={`brand ${className}`} aria-label="Trace">
            <img className="logo-for-light" src={`/logo${suffix}.png`} alt="Trace" height={height} width={width} style={{ height }} />
            <img className="logo-for-dark" src={`/logo${suffix}-light.png`} alt="" aria-hidden="true" height={height} width={width} style={{ height }} />
        </span>
    );
}
