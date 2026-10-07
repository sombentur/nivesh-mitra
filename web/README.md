# Nivesh Mitra — web app

The browser side of Nivesh Mitra: Next.js 16 (App Router), React 19 and Tailwind CSS 4. It talks only to the local
backend (`/api/*` is proxied to `http://127.0.0.1:8000`, or to `NM_BACKEND_URL` if set).

You don't run this folder on its own — use the `.bat` launchers in the project root. For development:

```
npm ci
npm run dev        # http://localhost:3000, needs the backend running
npm run lint
npx tsc --noEmit
npm run build
```

Design tokens live in `src/app/globals.css`, shared components in `src/components/ui.tsx`, the logo in `public/brand/`.
See the main [README](../README.md).
