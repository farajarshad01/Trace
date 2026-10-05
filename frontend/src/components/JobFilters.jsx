import Icon from "./Icon";


export default function JobFilters({ filters, onChange, companies }) {
    const set = (key) => (event) => onChange({ ...filters, [key]: event.target.value });

    return (
        <div className="toolbar glass">
            <div className="input-wrap grow">
                <Icon name="search" className="icon" />
                <input
                    className="field"
                    type="search"
                    placeholder="Search title, company, location or skill…"
                    value={filters.query}
                    onChange={set("query")}
                    aria-label="Search jobs"
                />
            </div>

            <select className="field" value={filters.company} onChange={set("company")} aria-label="Company">
                <option value="all">All companies</option>
                {companies.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>

            <select className="field" value={filters.minMatch} onChange={set("minMatch")} aria-label="Minimum match">
                <option value="0">Any match</option>
                <option value="50">50%+ match</option>
                <option value="70">70%+ match</option>
                <option value="80">80%+ match</option>
                <option value="90">90%+ match</option>
            </select>

            <select className="field" value={filters.sort} onChange={set("sort")} aria-label="Sort">
                <option value="match">Best match</option>
                <option value="newest">Newest</option>
            </select>
        </div>
    );
}
