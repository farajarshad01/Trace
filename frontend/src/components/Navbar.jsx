import Avatar from "./Avatar";
import Icon from "./Icon";
import Logo from "./Logo";
import { ThemeToggle } from "./Theme";


export const NAV_ITEMS = [
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "companies", label: "Companies", icon: "building" },
    { id: "applications", label: "Applications", icon: "clipboard" },
    { id: "resume", label: "Resume", icon: "file" },
];


/**
 * Desktop: a slim floating icon rail (labels appear on hover/focus).
 * Mobile (<= 920px): the original top bar plus a bottom tab bar.
 * Both are always rendered; CSS (shell.css) decides which one is visible.
 */
export default function Navbar({ page, onNavigate, user, onLogout }) {
    const email = user?.email || "";
    const name = user?.user_metadata?.full_name || email || "You";

    return (
        <>
            <aside className="rail glass strong" aria-label="Main">
                <button type="button" className="rail-logo" onClick={() => onNavigate("dashboard")} aria-label="Go to dashboard">
                    <Logo variant="mark" height={34} />
                </button>

                <nav className="rail-nav">
                    {NAV_ITEMS.map((item) => (
                        <button
                            key={item.id}
                            type="button"
                            className={`rail-item ${page === item.id ? "active" : ""}`}
                            data-label={item.label}
                            aria-label={item.label}
                            aria-current={page === item.id ? "page" : undefined}
                            onClick={() => onNavigate(item.id)}
                        >
                            <Icon name={item.icon} />
                        </button>
                    ))}
                </nav>

                <div className="rail-bottom">
                    <ThemeToggle />

                    <button type="button" className="btn btn-ghost btn-icon rail-signout" onClick={onLogout} aria-label="Sign out" data-label="Sign out">
                        <Icon name="logout" />
                    </button>

                    <span className="rail-user" title={email} data-label={email}>
                        <Avatar name={name} size="sm" round />
                    </span>
                </div>
            </aside>

            <header className="topbar glass strong">
                <button type="button" onClick={() => onNavigate("dashboard")} aria-label="Go to dashboard">
                    <Logo height={28} />
                </button>

                <div className="topbar-right">
                    <ThemeToggle />

                    <div className="user-chip">
                        <Avatar name={name} size="sm" round />
                        {email && <span className="email">{email}</span>}
                    </div>

                    <button type="button" className="btn btn-ghost btn-icon" onClick={onLogout} aria-label="Sign out" title="Sign out">
                        <Icon name="logout" />
                    </button>
                </div>
            </header>

            <nav className="bottom-nav glass strong" aria-label="Main">
                {NAV_ITEMS.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        className={page === item.id ? "active" : ""}
                        aria-current={page === item.id ? "page" : undefined}
                        onClick={() => onNavigate(item.id)}
                    >
                        <Icon name={item.icon} />
                        {item.label}
                    </button>
                ))}
            </nav>
        </>
    );
}
