"use client";

import { Send, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/hooks/useT";

// Cap at ~6 lines so longer asks scroll inside the textarea.
const MAX_TEXTAREA_HEIGHT_PX = 144;

export function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}) {
  const { t } = useT();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow; reset height each change so deletes can shrink.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT_PX)}px`;
  }, [value]);

  const trimmed = value.trim();
  const canSend = !disabled && !isStreaming && trimmed.length > 0;

  const submit = () => {
    if (!canSend) return;
    onSend(value);
    setValue("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // isComposing avoids submitting on IME commit.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={t("chat.input.placeholder")}
        rows={1}
        className="cosmic-input min-h-9 resize-none"
        disabled={disabled}
        aria-label={t("chat.input.label")}
      />
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          className="font-orbitron inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold uppercase transition-colors"
          style={{
            background: "rgba(255,112,67,0.15)",
            border: "1px solid rgba(255,112,67,0.4)",
            color: "var(--accent-coral)",
            letterSpacing: "0.16em",
          }}
          aria-label={t("chat.stopLabel")}
        >
          <Square className="h-3 w-3 fill-current" />
          {t("chat.stop")}
        </button>
      ) : (
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className="cosmic-btn-primary font-orbitron text-xs font-semibold uppercase"
          style={{
            padding: "0.65rem 1rem",
            letterSpacing: "0.16em",
          }}
          aria-label={t("chat.sendLabel")}
        >
          <Send className="h-3.5 w-3.5" />
          {t("chat.send")}
        </button>
      )}
    </div>
  );
}
