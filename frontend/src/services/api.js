import { supabase } from "./supabase";

// Set VITE_API_URL for deployed builds; defaults to the local backend.
const API_BASE_URL = (
    import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");


async function getAccessToken() {
    const { data: { session } } = await supabase.auth.getSession();

    return session?.access_token ?? null;
}


/**
 * FastAPI returns `detail` as a string for HTTPException but as an *array of
 * objects* for validation errors (422). Passing that array to `new Error()`
 * used to render "[object Object]" in the UI.
 */
function errorMessage(data, status) {
    const detail = data?.detail;

    if (typeof detail === "string" && detail) return detail;

    if (Array.isArray(detail) && detail.length) {
        return detail
            .map((item) => {
                const field = Array.isArray(item.loc)
                    ? String(item.loc[item.loc.length - 1]).replace(/_/g, " ")
                    : "";
                const msg = String(item.msg || "Invalid value")
                    .replace(/^Value error, /, "");

                return field && field !== "body" ? `${field}: ${msg}` : msg;
            })
            .join(". ");
    }

    return `Request failed (${status}). Please try again.`;
}


async function apiRequest(endpoint, options = {}) {
    const token = await getAccessToken();
    const isFormData = options.body instanceof FormData;

    const headers = { ...(options.headers || {}) };

    if (!isFormData) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;

    try {
        response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers,
        });
    } catch {
        throw new Error(
            "Can't reach the Trace server. Check your connection and that the backend is running."
        );
    }

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const error = new Error(errorMessage(data, response.status));

        error.status = response.status;
        error.retryAfter = Number(response.headers.get("Retry-After")) || null;

        throw error;
    }

    const text = await response.text();

    if (!text || text === "null") return null;

    try {
        return JSON.parse(text);
    } catch {
        return null;
    }
}


export async function checkApiHealth() {
    const response = await fetch(`${API_BASE_URL}/api/health`);

    if (!response.ok) throw new Error("API health check failed.");

    return response.json();
}

export const getCurrentUser = () => apiRequest("/api/auth/me");

export function uploadResume(file) {
    const formData = new FormData();

    formData.append("file", file);

    return apiRequest("/api/resumes/upload", { method: "POST", body: formData });
}

export const getCurrentResume = () => apiRequest("/api/resumes/current");

export const getRoles = () => apiRequest("/api/roles");

export const createRole = (roleTitle) =>
    apiRequest("/api/roles", {
        method: "POST",
        body: JSON.stringify({ role_title: roleTitle }),
    });

export const deleteRole = (roleId) =>
    apiRequest(`/api/roles/${roleId}`, { method: "DELETE" });

export const getSources = () => apiRequest("/api/sources");

export const createSource = (companyName, careerUrl) =>
    apiRequest("/api/sources", {
        method: "POST",
        body: JSON.stringify({ company_name: companyName, career_url: careerUrl }),
    });

export const deleteSource = (sourceId) =>
    apiRequest(`/api/sources/${sourceId}`, { method: "DELETE" });

export const getJobs = (limit = 200) => apiRequest(`/api/jobs?limit=${limit}`);

export const getJob = (jobId) => apiRequest(`/api/jobs/${jobId}`);

export const getApplications = () => apiRequest("/api/applications");

export const getApplication = (jobId) => apiRequest(`/api/applications/${jobId}`);

export const updateApplication = (jobId, status, notes) =>
    apiRequest(`/api/applications/${jobId}`, {
        method: "PUT",
        body: JSON.stringify({ status, notes }),
    });

export const deleteApplication = (jobId) =>
    apiRequest(`/api/applications/${jobId}`, { method: "DELETE" });
