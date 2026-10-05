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


export default function Navbar({ page, onNavigate, user, onLogout }) {
    const email = user?.email || "";
    const name = user?.user_metadata?.full_name || email || "You";

    return (
        <>
            <header className="topbar glass strong">
                <button type="button" onClick={() => onNavigate("dashboard")} aria-label="Go to dashboard">
                    <Logo height={28} />
                </button>

                <nav className="nav-tabs" aria-label="Main">
                    {NAV_ITEMS.map((item) => (
                        <button
                            key={item.id}
                            type="button"
                            className={`nav-tab ${page === item.id ? "active" : ""}`}
                            aria-current={page === item.id ? "page" : undefined}
                            onClick={() => onNavigate(item.id)}
                        >
                            <Icon name={item.icon} />
                            {item.label}
                        </button>
                    ))}
                </nav>

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
