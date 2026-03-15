"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { getLatestChatMessages, sendChatMessage } from "@/lib/api";

function parseAssistantMessage(text) {
  if (!text) return { recipeTitle: null, nutrition: null, rationale: null };
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  let recipeTitle = null;
  let nutrition = null;
  const body = [];

  for (const line of lines) {
    if (line.startsWith("Recommendation:")) {
      recipeTitle = line.replace("Recommendation:", "").trim();
    } else if (line.startsWith("Nutrition:")) {
      nutrition = line.replace("Nutrition:", "").trim();
    } else {
      body.push(line);
    }
  }

  return { recipeTitle, nutrition, rationale: body.join(" ") };
}

function AiAvatar() {
  return (
    <div className="shrink-0 flex items-center justify-center size-8 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm">
      <Icon name="nutrition" className="text-base" />
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-2.5">
      <AiAvatar />
      <div className="rounded-2xl rounded-tl-sm bg-white border border-slate-100 shadow-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.3s]" />
          <span className="size-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.15s]" />
          <span className="size-2 rounded-full bg-emerald-400 animate-bounce" />
          <span className="ml-1.5 text-xs text-slate-400 font-medium">Thinking...</span>
        </div>
      </div>
    </div>
  );
}

function AssistantBubble({ text, recommendationId }) {
  const { recipeTitle, nutrition, rationale } = parseAssistantMessage(text);
  const hasStructured = recipeTitle || nutrition;

  return (
    <div className="flex items-start gap-2.5 max-w-[85%]">
      <AiAvatar />
      <div className="flex flex-col gap-2 min-w-0">
        <div className="rounded-2xl rounded-tl-sm bg-white border border-slate-100 shadow-sm px-4 py-3 text-sm text-slate-700 leading-relaxed">
          {hasStructured ? (
            <div className="space-y-2">
              {recipeTitle && (
                <p className="font-bold text-slate-900">{recipeTitle}</p>
              )}
              {rationale && (
                <p className="text-slate-600 text-sm leading-relaxed">{rationale}</p>
              )}
              {nutrition && (
                <div className="flex items-center gap-1.5 pt-2 border-t border-slate-100">
                  <Icon name="local_fire_department" className="text-orange-400 text-sm shrink-0" />
                  <span className="text-xs font-semibold text-slate-500">{nutrition}</span>
                </div>
              )}
            </div>
          ) : (
            <p className="whitespace-pre-line">{text}</p>
          )}
        </div>

        {recommendationId && (
          <Link
            href={`/dashboard/recipes/${recommendationId}`}
            className="self-start flex items-center gap-1.5 rounded-xl bg-emerald-50 border border-emerald-200 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 transition-colors"
          >
            <Icon name="restaurant_menu" className="text-sm" />
            View full recipe
            <Icon name="arrow_forward" className="text-xs" />
          </Link>
        )}
      </div>
    </div>
  );
}

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%] rounded-2xl rounded-tr-sm bg-gradient-to-br from-emerald-500 to-teal-500 px-4 py-3 text-sm text-white shadow-sm shadow-emerald-100">
        {text}
      </div>
    </div>
  );
}

function EmptyState({ onPrompt }) {
  const suggestions = [
    { icon: "timer", text: "Quick 15-min meal idea" },
    { icon: "eco", text: "Vegetarian under 500 cal" },
    { icon: "savings", text: "Budget-friendly meal plan" },
    { icon: "fitness_center", text: "High protein post-workout" },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center space-y-5">
      <div className="flex items-center justify-center size-14 rounded-2xl bg-gradient-to-br from-emerald-100 to-teal-100 text-emerald-600">
        <Icon name="nutrition" className="text-3xl" />
      </div>
      <div className="space-y-1">
        <p className="font-bold text-slate-800">Your Personal Nutrition AI</p>
        <p className="text-sm text-slate-400 max-w-xs">
          Ask me to plan meals, adapt to your schedule, or optimize for your goals.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
        {suggestions.map(({ icon, text }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPrompt(text)}
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3 py-2.5 text-left text-xs font-medium text-slate-700 hover:border-emerald-300 hover:bg-emerald-50 transition-colors shadow-sm"
          >
            <Icon name={icon} className="text-base text-emerald-500 shrink-0" />
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollViewportRef = useRef(null);
  const inputRef = useRef(null);

  useToastFeedback({ error, clearError: () => setError("") });

  useEffect(() => {
    let active = true;
    async function load() {
      setLoadingHistory(true);
      try {
        const events = await getLatestChatMessages(30);
        if (!active) return;
        const rows = [...events].reverse().map((event) => ({
          id: `${event.source || "legacy"}-${event.role || "user"}-${event.event_id}`,
          role: event.role || "user",
          text: event.message,
          createdAt: event.created_at,
          pending: false,
          recommendation: event.recommendation_id
            ? { recommendation_id: event.recommendation_id }
            : null,
        }));
        setMessages(rows);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load chat history");
      } finally {
        if (active) setLoadingHistory(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const viewport = scrollViewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: loadingHistory ? "auto" : "smooth" });
  }, [messages.length, loadingHistory]);

  const quickPrompts = useMemo(() => [
    "Make it vegetarian and under 500 calories",
    "I only have 15 minutes, suggest a quick meal",
    "Reduce grocery cost for the next meal plan",
    "High protein meal using my pantry",
  ], []);

  async function handleSend(messageText) {
    const trimmed = (typeof messageText === "string" ? messageText : input).trim();
    if (!trimmed || sending) return;

    setError("");
    setSending(true);
    const nowIso = new Date().toISOString();
    const pendingAssistantId = `pending-a-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: `local-u-${Date.now()}`, role: "user", text: trimmed, createdAt: nowIso, pending: false },
      { id: pendingAssistantId, role: "assistant", text: "", createdAt: nowIso, pending: true, recommendation: null },
    ]);
    setInput("");
    inputRef.current?.focus();

    try {
      const result = await sendChatMessage(trimmed, { autoReplan: true });
      const rec = result.recommendation;
      const assistantText = result.assistant_message || (rec
        ? [
            `Recommendation: ${rec.decision?.recipe_title || "Suggested meal"}`,
            rec.decision?.rationale || "",
            `Nutrition: ${rec.meal_plan?.nutrition_summary?.calories || 0} kcal • ${rec.meal_plan?.nutrition_summary?.protein_g || 0}g protein`,
          ].filter(Boolean).join("\n")
        : "Message received. Share more constraints and I can generate a full meal plan.");

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === pendingAssistantId
            ? { id: `a-${result.event_id}-${Date.now()}`, role: "assistant", text: assistantText, createdAt: new Date().toISOString(), recommendation: rec || null, pending: false }
            : msg
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === pendingAssistantId
            ? { ...msg, text: "Something went wrong. Please try again.", pending: false }
            : msg
        )
      );
      setError(err.message || "Failed to send message");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col h-full min-h-0 -m-6">
      {/* Header */}
      <header className="flex items-center gap-3 px-5 py-3.5 border-b border-slate-100 bg-white/80 backdrop-blur flex-shrink-0">
        <div className="flex items-center justify-center size-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm">
          <Icon name="nutrition" className="text-lg" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-slate-900">Personal Nutrition AI</h1>
          <p className="text-xs text-emerald-600 font-medium flex items-center gap-1">
            <span className="size-1.5 bg-emerald-500 rounded-full animate-pulse" />
            Online & ready to replan
          </p>
        </div>
      </header>

      {/* Messages */}
      <div
        ref={scrollViewportRef}
        className="flex-1 overflow-y-auto px-4 py-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="mx-auto w-full max-w-2xl space-y-4">
          {loadingHistory && (
            <div className="flex justify-center py-6">
              <span className="text-xs text-slate-400 animate-pulse">Loading conversation...</span>
            </div>
          )}

          {messages.length === 0 && !loadingHistory && (
            <EmptyState onPrompt={(text) => handleSend(text)} />
          )}

          {messages.map((message) =>
            message.pending ? (
              <TypingIndicator key={message.id} />
            ) : message.role === "user" ? (
              <UserBubble key={message.id} text={message.text} />
            ) : (
              <AssistantBubble
                key={message.id}
                text={message.text}
                recommendationId={message.recommendation?.recommendation_id}
              />
            )
          )}
        </div>
      </div>

      {/* Footer */}
      <footer className="flex-shrink-0 border-t border-slate-100 bg-white/90 backdrop-blur px-4 pt-2.5 pb-4 space-y-2">
        {/* Quick prompts */}
        <div className="max-w-2xl mx-auto">
          <div className="flex gap-2 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handleSend(prompt)}
                disabled={sending}
                className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 font-medium hover:bg-emerald-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="max-w-2xl mx-auto flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend(input);
              }
            }}
            placeholder="Ask about meals, nutrition, or recipes..."
            className="flex-1 bg-slate-50 border border-slate-200 rounded-2xl py-3 px-4 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 transition-all"
            aria-label="Chat message"
          />
          <button
            type="button"
            onClick={() => handleSend(input)}
            disabled={sending || !input.trim()}
            className="shrink-0 size-11 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white flex items-center justify-center shadow-sm hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            aria-label="Send message"
          >
            <Icon name={sending ? "hourglass_top" : "send"} className="text-base" />
          </button>
        </div>
      </footer>
    </div>
  );
}
