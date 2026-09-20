# Frontend - Agent Instructions

**IMPORTANT**: When the user corrects you about a convention, pattern, structure, coding style, or gotcha — update this AGENTS.md to capture it so the lesson persists across sessions.

## Project Structure

```
app/
├── src/
│   ├── App.tsx                  # Root component
│   ├── main.tsx                 # Entry point
│   ├── pages/                   # Page components
│   ├── components/              # UI components
│   ├── hooks/                   # Custom React hooks
│   ├── lib/                     # Shared library functions (axios instance, etc.)
│   ├── schemas/
│   │   └── backend/             # ⚠️ GENERATED — DO NOT EDIT (run pnpm gen:all)
│   ├── types/
│   │   ├── backend/             # ⚠️ GENERATED — DO NOT EDIT (run pnpm gen:all)
│   │   └── websocket/           # ⚠️ GENERATED — DO NOT EDIT (run pnpm gen:ws)
│   └── assets/                  # Images, icons
├── scripts/                     # Code generation scripts
│   ├── generate-schemas.ts      # OpenAPI → Zodios clients
│   ├── generate-types.ts        # OpenAPI → TypeScript types
│   └── generate-ws-types.ts     # AsyncAPI → WebSocket types
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── eslint.config.js
```

## Commands

| Command          | Description                                |
| ---------------- | ------------------------------------------ |
| `pnpm dev`       | Start dev server at http://localhost:5173   |
| `pnpm build`     | Production build                           |
| `pnpm lint`      | ESLint                                     |
| `pnpm gen:all`   | Regenerate all API clients from backend    |
| `pnpm gen:schema`| Generate Zodios schemas from OpenAPI       |
| `pnpm gen:type`  | Generate TypeScript types from OpenAPI     |
| `pnpm gen:ws`    | Generate WebSocket types from AsyncAPI     |

## Code Style

- Use ES modules (`import/export`), not CommonJS (`require`)
- Destructure imports when possible
- Use Tailwind CSS classes, avoid inline styles
- Prefer functional components with hooks
- Follow existing component patterns in `src/components/`
- Only run linting/formatting/typechecking at the end of a feature implementation or bug fix, not after every small change. Stay calm and batch it.

### Component Organization

Components should be organized by domain:

```
src/components/{domain}/
├── detail/            # Detail/view pages
├── list/              # List/table views
└── shared/            # Shared components within domain
```

**Creating New Components:**

1. Place in appropriate `src/components/<domain>/` folder
2. Style with Tailwind classes
3. **NEVER put UI logic in pages/routes** - only routing logic belongs there

## Data Loading

Components can use generated API clients to fetch data. Use hooks for data fetching patterns.

## API Client Usage

**Always use generated API client methods** — never raw axios. Generated clients provide type safety and request validation.

**Always use schemas from** `src/schemas/backend/` for validation.

**API client calling convention (Zodios):**

```tsx
// GET methods - params/queries as first (and only) argument
await ticketsApiClient.ticketsRetrieve({
  params: { ticketId },
});

await ticketsApiClient.ticketsList({
  queries: { pageSize: 20 },
});

// POST/PUT/PATCH with body - body first, then params/queries
await ticketsApiClient.ticketsPartialUpdate(
  { title: 'New Title' },  // body (first param)
  { params: { ticketId } }  // params/queries (second param)
);

// POST without body - use undefined
await ticketsApiClient.ticketsCreate(
  undefined,  // no body
  { params: { ticketId } }
);
```

**Pattern summary:**
- **GET/DELETE**: `method({ params, queries })`
- **POST/PUT/PATCH with body**: `method(body, { params, queries })`
- **POST/PATCH without body**: `method(undefined, { params, queries })`

## WebSocket Usage

Uses `react-use-websocket` for WebSocket connections. Types are auto-generated from Backend AsyncAPI schema.

```tsx
import useWebSocket from 'react-use-websocket';

// WebSocket types are generated in src/types/websocket/
```

## Generated Code - DO NOT EDIT

These directories are auto-generated and should never be manually edited:

- `src/schemas/backend/` - Zod validation schemas (from Backend OpenAPI)
- `src/types/backend/` - TypeScript interfaces (from Backend OpenAPI)
- `src/types/websocket/` - WebSocket message types (from Backend AsyncAPI)

**Regenerate** (backend must be running at :8000):

- `pnpm gen:all` - Regenerate all backend API clients
- `pnpm gen:ws` - Regenerate WebSocket types

## Warnings & Gotchas

1. **Backend must be running** at `http://localhost:8000` for `pnpm gen:all`
2. **Never edit generated files** in `src/schemas/backend/`, `src/types/backend/`, `src/types/websocket/`
3. **Zodios clients** provide type-safe API calls with Zod runtime validation
4. **TanStack Router** for type-safe routing
5. **zustand** for state management
