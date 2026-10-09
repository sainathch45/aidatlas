// Maps JS API keys are inherently public (they ship in every page that
// uses them) -- the real security boundary is the HTTP-referrer
// restriction set on the key in the Cloud Console, not secrecy here.
// Backend keys (Gemini, service accounts) never go in this file.
const AIDATLAS_CONFIG = {
  API_BASE_URL: "http://127.0.0.1:8080",
  GOOGLE_MAPS_API_KEY: "AIzaSyCu6xIYV6B-yIyoHDzY4PCHwSmrRN5fVZk",
};
