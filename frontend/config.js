// Maps JS API keys are inherently public (they ship in every page that
// uses them) -- the real security boundary is the HTTP-referrer
// restriction set on the key in the Cloud Console, not secrecy here.
// Backend keys (Gemini, service accounts) never go in this file.
const AIDATLAS_CONFIG = {
  API_BASE_URL: "https://aidatlas-api-866617346749.asia-southeast1.run.app",
  GOOGLE_MAPS_API_KEY: "AIzaSyCu6xIYV6B-yIyoHDzY4PCHwSmrRN5fVZk",
};
