# Frontend — Multi-Agent Astronomy & Learning System

## Tổng quan

Frontend cho hệ thống đa tác nhân hỗ trợ học tập và phân tích dữ liệu thiên văn.
Giao diện cho: Multi-Agent chat, NotebookLM (Q&A, Summarize, Quiz, Flashcard), và Astronomy data visualization.

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| Animation | Framer Motion |
| UI Components | shadcn/ui |
| State Management | Zustand |
| Server State / Cache | TanStack Query v5 |
| HTTP Client | Axios |
| Package Manager | pnpm |
| Node version | 20+ |

## Cấu trúc thư mục

```
frontend/
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── .env.local                     # Biến môi trường (không commit)
├── .env.example                   # Mẫu biến môi trường
│
├── public/
│   ├── icons/
│   ├── fonts/
│   └── images/
│       └── astronomy/             # Ảnh thiên văn tĩnh (background, placeholder)
│
└── src/
    ├── app/                       # Next.js App Router
    │   ├── layout.tsx             # Root layout (font, theme provider, query client)
    │   ├── page.tsx               # Landing page
    │   │
    │   ├── (auth)/                # Route group: không có layout dashboard
    │   │   ├── login/
    │   │   │   └── page.tsx
    │   │   └── register/
    │   │       └── page.tsx
    │   │
    │   ├── (dashboard)/           # Route group: có Sidebar + Navbar
    │   │   ├── layout.tsx         # Dashboard layout chung
    │   │   ├── page.tsx           # Dashboard home / overview
    │   │   │
    │   │   ├── agents/
    │   │   │   ├── page.tsx       # Danh sách agents
    │   │   │   └── [id]/
    │   │   │       └── page.tsx   # Chat với agent cụ thể (streaming)
    │   │   │
    │   │   ├── notebook/
    │   │   │   ├── page.tsx       # Danh sách notebooks
    │   │   │   └── [id]/
    │   │   │       ├── page.tsx   # Notebook workspace (upload + Q&A)
    │   │   │       ├── quiz/
    │   │   │       │   └── page.tsx   # Làm quiz
    │   │   │       └── flashcards/
    │   │   │           └── page.tsx   # Ôn flashcard
    │   │   │
    │   │   └── astronomy/
    │   │       ├── page.tsx       # Astronomy dashboard
    │   │       ├── analyze/
    │   │       │   └── page.tsx   # Upload FITS & phân tích
    │   │       └── catalog/
    │   │           └── page.tsx   # Tìm kiếm catalog (Simbad, NED)
    │   │
    │   └── api/
    │       └── proxy/
    │           └── [...path]/
    │               └── route.ts   # Proxy tới FastAPI backend (tránh CORS)
    │
    ├── components/
    │   ├── ui/                    # shadcn/ui base components (auto-generated)
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── dialog.tsx
    │   │   ├── input.tsx
    │   │   ├── badge.tsx
    │   │   └── ...
    │   │
    │   ├── common/                # Dùng chung toàn app
    │   │   ├── Navbar.tsx
    │   │   ├── Sidebar.tsx
    │   │   ├── PageLoader.tsx     # Full-page loading với animation
    │   │   ├── ErrorBoundary.tsx
    │   │   └── ThemeToggle.tsx    # Dark / light mode
    │   │
    │   ├── agents/
    │   │   ├── AgentCard.tsx          # Card hiển thị thông tin agent
    │   │   ├── AgentChatWindow.tsx    # Chat UI với streaming response
    │   │   ├── AgentStatusBadge.tsx   # Badge: running / idle / error
    │   │   └── AgentTaskFlow.tsx      # Visualize pipeline các agent đang chạy
    │   │
    │   ├── notebook/
    │   │   ├── NotebookCard.tsx       # Card notebook trong danh sách
    │   │   ├── DocumentUploader.tsx   # Drag & drop upload PDF/txt
    │   │   ├── QAPanel.tsx            # Panel hỏi đáp từ tài liệu
    │   │   ├── SummaryView.tsx        # Hiển thị tóm tắt có animation
    │   │   ├── QuizCard.tsx           # Card câu hỏi trắc nghiệm
    │   │   └── FlashcardDeck.tsx      # Deck flashcard có flip animation
    │   │
    │   └── astronomy/
    │       ├── FitsViewer.tsx         # Hiển thị ảnh từ file FITS
    │       ├── StarCatalogTable.tsx   # Bảng kết quả tìm kiếm catalog
    │       ├── DataChart.tsx          # Biểu đồ phân tích (Recharts / D3)
    │       └── ReportViewer.tsx       # Xem báo cáo phân tích
    │
    ├── animations/                # Framer Motion variants tái sử dụng
    │   ├── fade.ts                # fadeIn, fadeInUp, fadeOut
    │   ├── slide.ts               # slideInLeft, slideInRight, slideUp
    │   ├── stagger.ts             # staggerContainer, staggerItem
    │   └── page-transition.ts     # Transition khi chuyển trang
    │
    ├── hooks/                     # Custom React hooks
    │   ├── useAgentStream.ts      # Hook xử lý SSE streaming từ agent
    │   ├── useNotebook.ts         # Hook CRUD notebook + upload
    │   ├── useAstronomy.ts        # Hook phân tích & catalog search
    │   └── useDebounce.ts         # Debounce input search
    │
    ├── stores/                    # Zustand global stores
    │   ├── agentStore.ts          # Trạng thái agents đang chạy
    │   ├── notebookStore.ts       # Notebook đang mở, tài liệu đã upload
    │   ├── sessionStore.ts        # Session hội thoại hiện tại
    │   └── uiStore.ts             # Theme, sidebar open/close, modal state
    │
    ├── services/                  # API call functions (dùng với TanStack Query)
    │   ├── api.ts                 # Axios instance, interceptors, base URL
    │   ├── agentService.ts        # runAgent(), getAgents(), getAgentStatus()
    │   ├── notebookService.ts     # createNotebook(), uploadDoc(), getQA()...
    │   └── astronomyService.ts    # uploadFits(), analyze(), searchCatalog()
    │
    ├── types/                     # TypeScript type definitions
    │   ├── agent.types.ts
    │   ├── notebook.types.ts
    │   ├── astronomy.types.ts
    │   └── api.types.ts           # ApiResponse<T>, PaginatedResponse<T>...
    │
    ├── lib/                       # Pure utility functions
    │   ├── utils.ts               # cn() (classnames), date format, truncate...
    │   ├── constants.ts           # ROUTES, API_ENDPOINTS, PAGE_TITLES
    │   └── validators.ts          # Zod schemas cho form validation
    │
    └── styles/
        └── globals.css            # Tailwind base + CSS variables (theme colors)
```

## Quy tắc đặt tên

| Thành phần | Convention | Ví dụ |
|---|---|---|
| Component | PascalCase | `AgentChatWindow.tsx` |
| Hook | camelCase + `use` prefix | `useAgentStream.ts` |
| Store | camelCase + `Store` suffix | `agentStore.ts` |
| Service | camelCase + `Service` suffix | `notebookService.ts` |
| Type/Interface | PascalCase + `Types` file | `Agent`, `NotebookResponse` |
| Animation variant | camelCase mô tả | `fadeInUp`, `staggerContainer` |
| Constant | UPPER_SNAKE_CASE | `API_BASE_URL`, `MAX_FILE_SIZE` |
| Folder | kebab-case hoặc camelCase | `agents/`, `notebook/` |

## Animation Pattern (Framer Motion)

```typescript
// animations/fade.ts
export const fadeInUp = {
  initial:    { opacity: 0, y: 20 },
  animate:    { opacity: 1, y: 0 },
  exit:       { opacity: 0, y: -10 },
  transition: { duration: 0.3, ease: "easeOut" }
}

export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.08 } }
}

// Dùng trong component — stagger list items
<motion.ul variants={staggerContainer} animate="animate">
  {items.map(item => (
    <motion.li key={item.id} variants={fadeInUp}>
      <ItemCard item={item} />
    </motion.li>
  ))}
</motion.ul>
```

## State Management Pattern

```
Server state  → TanStack Query  (API data, cache, loading/error)
Global UI     → Zustand store   (theme, sidebar, modal, session)
Local UI      → useState        (form input, toggle, hover)
```

## Luồng data

```
Page (Next.js route)
  → Custom Hook        (useNotebook, useAgentStream)
    → Service          (TanStack Query + Axios)
      → /api/proxy     (Next.js route → FastAPI backend)
    ← Cache tự động
  ← Zustand store      (global UI state sync)
← Component render     (+ Framer Motion animation)
```

## Biến môi trường (.env.example)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=AstroLearn
```

## Khởi chạy (development)

```bash
# Cài dependencies
pnpm install

# Chạy dev server
pnpm dev          # http://localhost:3000

# Build production
pnpm build
pnpm start
```

## Ghi chú quan trọng

- **Không dùng `localStorage` / `sessionStorage`** trong component — dùng Zustand + `persist` middleware nếu cần lưu local.
- **Streaming response** từ agent dùng `EventSource` (SSE) trong `useAgentStream.ts`, không dùng fetch thông thường.
- **shadcn/ui** chỉ copy component vào `components/ui/`, không phải thư viện — có thể sửa tự do.
- **Framer Motion variants** đặt tất cả trong `animations/` để tái sử dụng, không inline trong component.
- **API proxy** ở `/api/proxy/[...path]` giúp ẩn backend URL và tránh CORS khi deploy.