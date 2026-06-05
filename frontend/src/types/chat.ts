export type RagSource = {
  filename: string;
  friendly_name?: string;
  snippet: string;
};

export type ChatMode = "tutor" | "student";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: RagSource[];
  is_cached?: boolean;
};

export type ChatApiResponse = {
  session_id: string;
  response: string;
  sources?: RagSource[];
  is_cached?: boolean;
};
