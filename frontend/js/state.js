import { api } from "./api.js";
export const state = { user: null, audio: null };
export const homeFor = (u) => (u?.role === "ADMIN" ? "/admin/dashboard" : "/user/home");
export async function refreshUser() { try { state.user = (await api("/auth/me")).user; } catch { state.user = null; } return state.user; }
// Three-step login: identify -> password (OTP emailed) -> verify (session created here).
export const loginIdentify = (identifier, login_as) => api("/auth/login/identify", { method: "POST", body: { identifier, login_as } });
export const loginPassword = (ticket, password) => api("/auth/login/password", { method: "POST", body: { ticket, password } });
export const loginResend = (ticket) => api("/auth/login/resend", { method: "POST", body: { ticket } });
export const loginVerify = (ticket, code) => api("/auth/login/verify", { method: "POST", body: { ticket, code } });  // -> { step:'pin', pin_set }
export async function loginPin(ticket, pin) { state.user = (await api("/auth/login/pin", { method: "POST", body: { ticket, pin } })).user; return state.user; }
export const resetRequest = (email) => api("/auth/password-reset/request", { method: "POST", body: { email } });
export const resetConfirm = (ticket, code, new_password, confirm_password) => api("/auth/password-reset/confirm", { method: "POST", body: { ticket, code, new_password, confirm_password } });
export async function logout() { try { await api("/auth/logout", { method: "POST" }); } finally { state.user = null; } }
export function setAudio(file, source, duration) { if (state.audio?.url) URL.revokeObjectURL(state.audio.url); state.audio = file ? { file, url: URL.createObjectURL(file), source, name: file.name, duration } : null; }
