import type { PoiResponse, RouteResponse, StartJobResponse, TripForm, TripJob } from "../types/trip";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";
const API_BASE_STORAGE_KEY = "tripweave-agent.api-base-url";
const LEGACY_API_BASE_STORAGE_KEY = "trip-agent.api-base-url";

export interface RuntimeSettingsStatus {
  llm_base_url: string;
  llm_model: string;
  openweather_api_host: string;
  amap_web_js_key: string;
  has_llm_api_key: boolean;
  has_amap_service_key: boolean;
  has_openweather_api_key: boolean;
  has_tavily_api_key: boolean;
}

export function getApiBase(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  const saved = window.localStorage.getItem(API_BASE_STORAGE_KEY)
    || window.localStorage.getItem(LEGACY_API_BASE_STORAGE_KEY);
  return saved?.trim().replace(/\/+$/, "") || DEFAULT_API_BASE;
}

export function setApiBase(value: string): string {
  const normalized = value.trim().replace(/\/+$/, "") || DEFAULT_API_BASE;
  window.localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
  return normalized;
}

export interface MapConfig {
  amap_js_key?: string;
  amap_security_js_code?: string;
}

export function staticMapUrl(city: string, keyword: string, center = "", zoom = 10, points = ""): string {
  const params = new URLSearchParams({
    city,
    keyword,
    limit: "8",
    center,
    zoom: String(zoom),
    size: "1024*420",
    v: String(Date.now()),
  });
  if (points) params.set("points", points);
  return `${getApiBase()}/api/map/static?${params.toString()}`;
}

export async function healthCheck(): Promise<{ status: string }> {
  return getJson("/health");
}

export async function fetchMapConfig(): Promise<MapConfig> {
  return getJson("/api/map/config");
}

export async function fetchRuntimeSettings(): Promise<{ success: boolean; data: RuntimeSettingsStatus }> {
  return getJson("/api/settings");
}

export async function saveRuntimeSettings(payload: Record<string, string>): Promise<{ success: boolean; data: RuntimeSettingsStatus }> {
  return postJson("/api/settings", payload);
}

export async function startTripPlan(payload: TripForm): Promise<StartJobResponse> {
  return postJson("/api/trip/plan/async", payload);
}

export async function getTripJob(jobId: string): Promise<TripJob> {
  return getJson(`/api/trip/jobs/${jobId}`);
}

export async function fetchPois(city: string, keyword: string): Promise<PoiResponse> {
  return getJson(`/api/map/poi?city=${encodeURIComponent(city)}&keyword=${encodeURIComponent(keyword)}&limit=8`);
}

export async function fetchAttractionPhoto(name: string, city: string): Promise<any> {
  const params = new URLSearchParams({ name, city });
  return getJson(`/api/poi/photo?${params.toString()}`);
}

export async function geocode(address: string, city: string): Promise<any> {
  return getJson(`/api/map/geocode?address=${encodeURIComponent(address)}&city=${encodeURIComponent(city)}`);
}

export async function fetchRoute(origin: string, destination: string, city: string, mode: string): Promise<RouteResponse> {
  const params = new URLSearchParams({ origin, destination, city, mode });
  return getJson(`/api/map/route?${params.toString()}`);
}

async function getJson(path: string): Promise<any> {
  const response = await fetch(`${getApiBase()}${path}`);
  return parseResponse(response);
}

async function postJson(path: string, body: unknown): Promise<any> {
  const response = await fetch(`${getApiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

async function parseResponse(response: Response): Promise<any> {
  let data: any = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  return data;
}
