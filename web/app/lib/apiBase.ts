const envApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

const guessApiBaseUrl = () => {
  if (envApiBaseUrl) {
    return envApiBaseUrl;
  }
  if (typeof window === "undefined") {
    return "http://localhost:4321";
  }
  const { hostname, port, protocol } = window.location;
  if (port === "1234") {
    return `${protocol}//${hostname}:4321`;
  }
  if (!port || port === "80" || port === "443") {
    return `${protocol}//${hostname}`;
  }
  return `${protocol}//${hostname}:4321`;
};

export const API_BASE_URL = guessApiBaseUrl();
