# JavaScript / TypeScript — Deep Patterns

Extended reference for the `human-like-code` skill. Read this when the user's task involves JS, TS, React, or Node.js backends.

---

## HTTP Client: Never Raw `fetch` in Business Logic

### ❌ AI Pattern
```typescript
const response = await fetch(`https://api.example.com/users/${userId}`);
if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
const data = await response.json();
```

### ✅ Human Pattern — Centralized Client
```typescript
// src/core/api/client.ts
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { env } from '@/core/config/env';
import { logger } from '@/core/utils/logger';

const httpClient: AxiosInstance = axios.create({
  baseURL: env.API_BASE_URL,
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor — attach auth token from session
httpClient.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor — log errors, normalize shape
httpClient.interceptors.response.use(
  (response) => response,
  (error) => {
    logger.error('HTTP request failed', {
      url: error.config?.url,
      status: error.response?.status,
      message: error.message,
    });
    return Promise.reject(error);
  },
);

export { httpClient };

// Usage:
import { httpClient } from '@/core/api/client';
const { data } = await httpClient.get<UserProfile>(`/v1/users/${userId}`);
```

---

## Caching: Environment-Safe with TTL

### ❌ AI Pattern — Breaks in SSR
```typescript
const cached = localStorage.getItem(`user_${userId}`);
if (cached) return JSON.parse(cached);
// ...
localStorage.setItem(`user_${userId}`, JSON.stringify(data));
```

`localStorage` throws in Node.js / SSR. Zero TTL means stale data lives forever.

### ✅ Human Pattern — In-Memory with TTL
```typescript
// src/core/cache/memory.ts
interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

class MemoryCache {
  private store = new Map<string, CacheEntry<unknown>>();

  get<T>(key: string): T | null {
    const entry = this.store.get(key) as CacheEntry<T> | undefined;
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return null;
    }
    return entry.value;
  }

  set<T>(key: string, value: T, options: { ttl: number }): void {
    this.store.set(key, { value, expiresAt: Date.now() + options.ttl });
  }

  invalidate(key: string): void {
    this.store.delete(key);
  }
}

export const memoryCache = new MemoryCache();

// Usage:
import { memoryCache } from '@/core/cache/memory';

const cached = memoryCache.get<UserProfile>(`user:${userId}`);
if (cached) return cached;
// ... fetch ...
memoryCache.set(`user:${userId}`, data, { ttl: 5 * 60 * 1000 }); // 5 min
```

---

## Error Handling: Sanitize at the Boundary

### ❌ AI Pattern — Leaks to UI
```typescript
} catch (error) {
  console.error("Error fetching user profile:", error);
  throw error; // raw Error, message could be "connect ECONNREFUSED 127.0.0.1:5432"
}
```

### ✅ Human Pattern — Structured Log, Clean Token
```typescript
// src/core/utils/logger.ts — structured logger (use pino in Node, console adapter in browser)
import pino from 'pino';
export const logger = pino({ level: process.env.LOG_LEVEL ?? 'info' });

// In service:
} catch (error) {
  logger.error({ userId, error }, 'Failed to retrieve user profile');
  throw new Error('PROFILE_FETCH_FAILED'); // stable string — UI can switch on this
}

// UI layer:
try {
  const profile = await getUserProfile(userId);
} catch (error) {
  if (error instanceof Error && error.message === 'PROFILE_FETCH_FAILED') {
    showToast('Could not load your profile. Please try again.');
  }
}
```

---

## TypeScript: Strict Types, Not `any`

```typescript
// ❌ AI — type safety abandoned
const processUserData = (data: any): any => {
  return data.users.map((u: any) => u.id);
};

// ✅ Human — explicit contracts, no escape hatches
interface RawUserListResponse {
  users: Array<{ id: string; status: 'active' | 'inactive' | 'suspended' }>;
  total: number;
}

const extractActiveUserIds = (response: RawUserListResponse): string[] => {
  return response.users
    .filter((user) => user.status === 'active')
    .map((user) => user.id);
};
```

### tsconfig.json — Always Strict
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true
  }
}
```

---

## React: Component Naming and Responsibility

### Naming Rules
```tsx
// ❌ AI — generic, vague
const UserComp = () => { ... }
const DataCard = () => { ... }
const HandleList = () => { ... }

// ✅ Human — specific single-responsibility names
const UserAvatarWithFallback = () => { ... }
const OrderSummaryCard = () => { ... }
const PaginatedProductList = () => { ... }
```

### Hook Naming
```tsx
// ❌ AI
const useData = () => { ... }
const useFetch = (url: string) => { ... }

// ✅ Human — domain-specific
const useAuthenticatedUserProfile = (userId: string) => { ... }
const usePaginatedOrderHistory = (filters: OrderFilters) => { ... }
```

### Props: Explicit Interfaces, Not Inline Objects
```tsx
// ❌ AI — buried, unnamed, hard to test
const UserCard = ({ name, email, onClick }: { name: string; email: string; onClick: () => void }) => { ... }

// ✅ Human — named, exportable, composable
interface UserCardProps {
  displayName: string;
  emailAddress: string;
  /** Called when the card is clicked — parent handles navigation */
  onSelectUser: (userId: string) => void;
  isLoadingProfile?: boolean;
}

export const UserProfileCard = ({
  displayName,
  emailAddress,
  onSelectUser,
  isLoadingProfile = false,
}: UserCardProps) => { ... }
```

### Separate Data Fetching from Rendering
```tsx
// ❌ AI — fetch inside render component
const UserDashboard = () => {
  const [users, setUsers] = useState([]);
  useEffect(() => {
    fetch('/api/users').then(r => r.json()).then(setUsers);
  }, []);
  return <div>{users.map(u => <div key={u.id}>{u.name}</div>)}</div>;
};

// ✅ Human — data in hook, rendering in component
// hooks/useEnrolledUsers.ts
export const useEnrolledUsers = () => {
  return useQuery({
    queryKey: ['enrolled-users'],
    queryFn: () => httpClient.get<User[]>('/v1/users'),
    staleTime: 5 * 60 * 1000,
  });
};

// components/UserDashboard.tsx
export const UserDashboard = () => {
  const { data: enrolledUsers, isLoading, error } = useEnrolledUsers();
  if (isLoading) return <UserDashboardSkeleton />;
  if (error) return <ErrorBoundaryFallback code="USER_LIST_UNAVAILABLE" />;
  return <UserGrid users={enrolledUsers} />;
};
```

---

## Environment Config: Validated at Startup

```typescript
// src/core/config/env.ts
import { z } from 'zod';

const envSchema = z.object({
  API_BASE_URL: z.string().url(),
  NEXT_PUBLIC_APP_ENV: z.enum(['development', 'staging', 'production']),
  CACHE_TTL_MS: z.coerce.number().default(300_000),
});

// Throws at startup if any required var is missing — fail fast, loudly
const parsed = envSchema.safeParse(process.env);
if (!parsed.success) {
  console.error('❌ Invalid environment variables:', parsed.error.format());
  process.exit(1);
}

export const env = parsed.data;
```

---

## Utility Functions: Pure and Central

```typescript
// src/core/utils/currency.ts

/**
 * Formats a number as a display currency string.
 * Central utility — locale and symbol changes need one edit here.
 */
export const toDisplayCurrency = (
  amount: number,
  currencyCode: string = 'USD',
  locale: string = 'en-US',
): string => {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currencyCode,
  }).format(amount);
};

// src/core/utils/date.ts
export const toRelativeTimeString = (date: Date): string => {
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  if (Math.abs(diffSeconds) < 60) return rtf.format(diffSeconds, 'second');
  const diffMinutes = Math.round(diffSeconds / 60);
  if (Math.abs(diffMinutes) < 60) return rtf.format(diffMinutes, 'minute');
  return rtf.format(Math.round(diffMinutes / 60), 'hour');
};
```

**Rules:**
- Use `Intl.*` APIs — never hand-roll date/currency formatting.
- Each util function: pure, zero side effects, one responsibility.
- Export from `src/core/utils/index.ts` for clean imports.

---

## Project Structure (Next.js / Node API)

```
src/
├── app/                  # Next.js app router pages
│   └── (dashboard)/
│       └── orders/
├── components/
│   ├── ui/               # Headless design system primitives
│   └── features/         # Domain-specific composite components
│       └── orders/
│           ├── OrderSummaryCard.tsx
│           └── PaginatedOrderList.tsx
├── hooks/                # All custom hooks (data + UI)
├── core/
│   ├── api/
│   │   └── client.ts     # Axios singleton
│   ├── cache/
│   │   └── memory.ts     # In-memory TTL cache
│   ├── config/
│   │   └── env.ts        # Validated env vars
│   └── utils/
│       ├── currency.ts
│       ├── date.ts
│       └── logger.ts
├── types/                # Shared TS interfaces / enums
└── lib/                  # Third-party SDK wrappers (Stripe, Supabase)
```
