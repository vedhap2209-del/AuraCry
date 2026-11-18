export class ApiError extends Error { constructor(m, status, data) { super(m); this.status = status; this.data = data; } }
const readCookie = (name) => document.cookie.split("; ").find((c) => c.startsWith(name + "="))?.split("=")[1];
export async function api(path, { method = "GET", body, form } = {}) {
  const o = { method, credentials: "same-origin", headers: {} };
  if (!["GET", "HEAD"].includes(method)) {              // double-submit CSRF token (server sets the csrf_token cookie)
    const t = readCookie("csrf_token");
    if (t) o.headers["X-CSRF-Token"] = decodeURIComponent(t);
  }
  if (form) o.body = form; else if (body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
  let res;
  try { res = await fetch("/api" + path, o); } catch { throw new ApiError("Cannot reach the server. Is the backend running?", 0); }
  let data = null; try { data = await res.json(); } catch {}
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("auracry-unauth"));
    throw new ApiError(data?.message || `Request failed (${res.status})`, res.status, data);
  }
  return data;
}
