import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Node global available in the Vite config context (not typed without @types/node).
declare const process: { env: Record<string, string | undefined> };

// The backend (FastAPI + Piper) is proxied under /api during dev so the
// front-end can call the self-hosted voice without CORS friction.
// Hardening headers for the served SPA. Kept dev-safe (no restrictive CSP that
// would break HMR); the production host/CDN should additionally send a full CSP.
const securityHeaders = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Honour an assigned PORT (tooling may pick a free one when 5173 is taken);
    // fall back to 5173 so plain `npm run dev` matches the README.
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    host: true, // bind 0.0.0.0 so other devices on the LAN can reach it
    headers: securityHeaders,
    proxy: {
      // Local dev proxies /api to the backend so the browser sees same-origin
      // (no CORS) and the auth cookie sticks on localhost. cookieDomainRewrite
      // strips any upstream cookie domain. Defaults to the local backend on
      // :8000; set VOXFORGE_LOCAL_API to point at a remote (e.g. the GCP host).
      '/api': {
        target: process.env.VOXFORGE_LOCAL_API || 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: true,
        cookieDomainRewrite: '',
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  // `vite preview` mimics production: add a real CSP here too.
  preview: {
    port: 4173,
    headers: {
      ...securityHeaders,
      'Content-Security-Policy':
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; " +
        "media-src 'self' blob:; connect-src 'self'; " +
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    },
  },
});
