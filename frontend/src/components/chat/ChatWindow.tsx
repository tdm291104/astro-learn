"use client";

import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { ContextBar } from "@/components/chat/ContextBar";
import { FitsIntentToolbar } from "@/components/chat/FitsIntentToolbar";
import { useChat } from "@/hooks/useChat";
import { useChatStore } from "@/stores/chatStore";

export function ChatWindow() {
  const { messages, isStreaming, error, streamPhase, send, stop } = useChat();
  // Read mode here (not in useChat) so the toolbar re-renders on tab switch.
  const mode = useChatStore((s) => s.mode);

  return (
    <div className="cosmic-card flex h-full min-h-0 w-full flex-col overflow-hidden p-0">
      <ContextBar />

      <ChatMessageList
        messages={messages}
        onExampleClick={send}
        onConfirmWebSearch={(q) => send(q, { forceWebSearch: true })}
        streamPhase={isStreaming ? streamPhase : null}
      />

      {error && !isStreaming && (
        <p
          className="font-exo2 px-5 pb-2 text-xs"
          style={{ color: "var(--accent-coral)" }}
        >
          {error}
        </p>
      )}

      <div
        className="space-y-2 px-5 py-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        {mode === "fits" && <FitsIntentToolbar />}
        <ChatInput
          onSend={send}
          onStop={stop}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
