export interface TripForm {
  city: string;
  start_date: string;
  days: number;
  travelers: number;
  max_budget: number;
  preferences: string[];
  pace: string;
  accommodation: string;
  transportation: string;
  special_requirements: string;
  include_packing: boolean;
  cities?: CitySegment[];
}

export interface CitySegment {
  city: string;
  days: number;
}

export interface Poi {
  id?: string;
  name?: string;
  type?: string;
  address?: string;
  rating?: string | number | null;
  cost?: string | number | null;
  photo_url?: string;
  photo_urls?: string[];
  location?: {
    longitude?: number | string | null;
    latitude?: number | string | null;
  };
}

export interface ItineraryAttraction extends Poi {
  visit_minutes?: number;
  transfer_minutes?: number;
  research_source?: boolean;
  research_candidate_name?: string;
}

export interface ItineraryDay {
  day: number;
  date?: string;
  city?: string;
  summary?: string;
  transportation?: string;
  total_minutes?: number;
  weather?: Record<string, any>;
  meals?: {
    lunch?: Poi;
    dinner?: Poi;
  };
  hotel?: Poi;
  attractions: ItineraryAttraction[];
}

export interface StructuredPlan {
  city: string;
  cities?: CitySegment[];
  start_date: string;
  days_count: number;
  travelers: number;
  preferences: string[];
  pace: string;
  accommodation: string;
  transportation: string;
  itinerary_days: ItineraryDay[];
  attractions: Poi[];
  restaurants: Poi[];
  hotels: Poi[];
  travel_insights?: Record<string, any>;
  weather: Record<string, any>;
  budget: Record<string, any>;
  budget_check: Record<string, any>;
  constraints: Record<string, any>;
  packing: Record<string, any>;
  content: string;
}

export interface KnowledgeGraph {
  nodes: Array<Record<string, any>>;
  edges: Array<Record<string, any>>;
  categories: Array<Record<string, any>>;
}

export interface TripJob {
  success: boolean;
  job_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "cancelling";
  created_at?: string;
  updated_at?: string;
  steps?: Array<Record<string, any>>;
  content?: string;
  step_count?: number;
  progress?: number;
  stage?: string;
  current_city?: string;
  warning?: string | null;
  error?: string | null;
  structured_plan?: StructuredPlan | null;
  knowledge_graph?: KnowledgeGraph | null;
}

export interface StartJobResponse {
  success: boolean;
  job_id: string;
  status: string;
}

export interface PoiResponse {
  ok: boolean;
  provider?: string;
  city?: string;
  keyword?: string;
  pois?: Poi[];
  error?: string;
}

export interface RouteResponse {
  ok: boolean;
  provider?: string;
  mode?: string;
  mode_used?: string;
  distance_meters?: number;
  duration_minutes?: number;
  origin?: string;
  destination?: string;
  error?: string;
}
