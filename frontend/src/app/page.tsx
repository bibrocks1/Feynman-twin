"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send, User, Brain, Loader2,
  Mic, MicOff, Volume2, VolumeX,
  GraduationCap, BookOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SourceBlueprint } from "@/components/SourceBlueprint";
import { normalizeSources } from "@/lib/sources";
import type { ChatApiResponse, ChatMessage, ChatMode, RagSource } from "@/types/chat";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// ─── Web Speech API types live in src/types/speech.d.ts ──────────────────────

// ─── Markdown stripping for TTS ───────────────────────────────────────────────
function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/(\*{1,3}|_{1,3})(.*?)\1/g, "$2")
    .replace(/`{1,3}[^`]*`{1,3}/g, "")
    .replace(/^>\s+/gm, "")
    .replace(/^[-*_]{3,}\s*$/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_~`]/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// ─── Select a male English voice ─────────────────────────────────────────────
function pickMaleVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const en = voices.filter((v) => v.lang.startsWith("en"));
  const malePriority = ["Google UK English Male", "Microsoft David", "Daniel", "Alex", "Fred"];
  for (const name of malePriority) {
    const match = en.find((v) => v.name.includes(name));
    if (match) return match;
  }
  return en[0] ?? voices[0] ?? null;
}

// ─── Mode toggle component ────────────────────────────────────────────────────
function ModeToggle({
  mode,
  onChange,
}: {
  mode: ChatMode;
  onChange: (m: ChatMode) => void;
}) {
  const isStudent = mode === "student";
  return (
    <div
      className="flex items-center gap-1 p-1 rounded-xl bg-white/5 border border-white/10"
      title={isStudent ? "Student Mode: you explain, Feynman evaluates" : "Tutor Mode: Feynman explains to you"}
    >
      {/* Tutor pill */}
      <button
        type="button"
        onClick={() => onChange("tutor")}
        className={`
          flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all duration-200
          ${!isStudent
            ? "bg-blue-600 text-white shadow-md shadow-blue-900/40"
            : "text-gray-400 hover:text-gray-200"
          }
        `}
      >
        <BookOpen size={12} />
        <span>Tutor</span>
      </button>

      {/* Student pill */}
      <button
        type="button"
        onClick={() => onChange("student")}
        className={`
          flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all duration-200
          ${isStudent
            ? "bg-violet-600 text-white shadow-md shadow-violet-900/40"
            : "text-gray-400 hover:text-gray-200"
          }
        `}
      >
        <GraduationCap size={12} />
        <span>Student</span>
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
export default function ChatDashboard() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello there! I'm Richard Feynman. What physics puzzle are we working on today?",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeSources, setActiveSources] = useState<RagSource[]>([]);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  // ── Mode state ────────────────────────────────────────────────────────────

  const [chatMode, setChatMode] = useState<ChatMode>("tutor");

  // ── Voice state ───────────────────────────────────────────────────────────
  const [isListening, setIsListening] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Scroll helpers ─────────────────────────────────────────────────────────
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(() => { scrollToBottom(); }, [messages]);

  // Keep Source Blueprint in sync with latest assistant turn that has sources
  useEffect(() => {
    const latestWithSources = [...messages]
      .reverse()
      .find((m) => m.role === "assistant" && m.sources && m.sources.length > 0);
    if (latestWithSources?.sources) {
      setActiveSources(latestWithSources.sources);
    }
  }, [messages]);

  // ── TTS speaker ───────────────────────────────────────────────────────────
  const speakText = useCallback((text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    if (isMuted) return;
    window.speechSynthesis.cancel();
    const clean = stripMarkdown(text);
    if (!clean) return;
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 0.95;
    utterance.pitch = 0.9;
    const assignVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      const voice = pickMaleVoice(voices);
      if (voice) utterance.voice = voice;
    };
    assignVoice();
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = assignVoice;
    }
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = (e) => {
      if (e.error !== "interrupted") console.error("SpeechSynthesis error:", e.error);
      setIsSpeaking(false);
    };
    window.speechSynthesis.speak(utterance);
  }, [isMuted]);

  // ── Auto-speak on new assistant messages ──────────────────────────────────
  const prevMessageCountRef = useRef(messages.length);
  useEffect(() => {
    const prevCount = prevMessageCountRef.current;
    prevMessageCountRef.current = messages.length;
    if (messages.length <= prevCount) return;
    const latest = messages[messages.length - 1];
    if (latest.role === "assistant" && latest.id !== "welcome") {
      speakText(latest.content);
    }
  }, [messages, speakText]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      window.speechSynthesis?.cancel();
    };
  }, []);

  // ── Microphone toggle ─────────────────────────────────────────────────────
  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }
    const SpeechRecognitionCtor =
      window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      alert("Speech Recognition is not supported in this browser. Try Chrome or Edge.");
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += transcript;
        else interim += transcript;
      }
      setInputValue(final || interim);
    };
    recognition.onend = () => { setIsListening(false); recognitionRef.current = null; };
    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error !== "aborted" && event.error !== "no-speech") {
        console.error("SpeechRecognition error:", event.error);
      }
      setIsListening(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    recognition.start();
  };

  // ── Mute toggle ───────────────────────────────────────────────────────────
  const toggleMute = () => {
    if (!isMuted) {
      window.speechSynthesis?.cancel();
      setIsSpeaking(false);
    }
    setIsMuted((prev) => !prev);
  };

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputValue.trim()) return;

    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    if (isListening) recognitionRef.current?.stop();

    const newMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
    };
    setMessages((prev) => [...prev, newMsg]);
    setInputValue("");
    setIsLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: newMsg.content,
          session_id: sessionId,
          mode: chatMode,
        }),
      });

      const data = (await res.json()) as ChatApiResponse & { detail?: string };

      if (!res.ok) {
        // Restore the user's text so they don't have to retype it
        setInputValue(newMsg.content);
        setIsLoading(false);
        const detail = data.detail ?? "The AI service is currently overloaded. Please try again in a moment.";
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now().toString(),
            role: "assistant",
            content: `Network Error: ${detail}`,
          },
        ]);
        return;
      }

      if (data.session_id && !sessionId) setSessionId(data.session_id);

      const sources = normalizeSources(data.sources);
      setActiveSources(sources);

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: data.response || "Something went wrong.",
          sources,
          is_cached: data.is_cached ?? false,
        },
      ]);
    } catch (err) {
      // Only reached on a true network failure (fetch threw — backend unreachable)
      console.error(err);
      setActiveSources([]);
      // Restore input so the user can retry without retyping
      setInputValue(newMsg.content);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: "Network Error: Could not reach the Digital Twin backend. Please check your connection and try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const isStudentMode = chatMode === "student";

  // ─────────────────────────────────────────────────────────────────────────
  if (!mounted) {
    return <div className="flex h-screen bg-gray-900"></div>;
  }
  return (
    <div className="flex h-screen w-full bg-background overflow-hidden font-sans">

      {/* ── Left Sidebar ───────────────────────────────────────────────────── */}
      <motion.div
        initial={{ x: -300, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="hidden md:flex w-80 glass-panel border-r border-white/10 flex-col p-6 m-4 rounded-2xl relative z-10 min-h-0"
      >
        <div className="flex items-center gap-3 mb-6 shrink-0">
          <div className="p-2 bg-blue-500/20 rounded-lg border border-blue-500/30">
            <Brain className="w-6 h-6 text-blue-400" />
          </div>
          <h2 className="text-lg font-semibold text-white">Memory Profile</h2>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar min-h-0">
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-white/5 border border-white/10 text-sm text-gray-300 leading-relaxed shadow-inner">
              <p className="mb-2 font-medium text-blue-300">Extracted User Traits:</p>
              The user is a first-year undergraduate physics student who is struggling with
              understanding quantum mechanics, particularly the probability amplitude concept,
              finding it counter-intuitive. They are curious, engaged, and willing to read
              specific physics literature (like QED) to deepen their understanding.
            </div>

            <p className="text-xs text-gray-500 italic text-center">
              (This profile dynamically updates every 10 messages based on Gemini 2.5 Flash
              extraction)
            </p>
          </div>

          <SourceBlueprint sources={activeSources} />
        </div>
      </motion.div>

      {/* ── Main Chat Area ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col h-full relative p-4 md:p-8 md:pl-4">

        {/* Header */}
        <div className="flex items-center justify-between mb-6 glass px-6 py-4 rounded-2xl z-10 shadow-lg">
          <div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300">
              Richard Feynman
            </h1>
            <p className="text-xs text-gray-400">Digital Twin (v1.0)</p>
          </div>

          <div className="flex items-center gap-3 flex-wrap justify-end">
            {/* TTS mute/unmute toggle */}
            <button
              onClick={toggleMute}
              title={isMuted ? "Unmute voice" : "Mute voice"}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium
                border transition-all duration-200
                ${isMuted
                  ? "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10 hover:text-gray-200"
                  : isSpeaking
                    ? "bg-cyan-500/20 border-cyan-400/50 text-cyan-300 animate-pulse"
                    : "bg-cyan-500/15 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/25"
                }
              `}
            >
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
              <span className="hidden sm:inline">
                {isMuted ? "Voice Off" : isSpeaking ? "Speaking…" : "Voice On"}
              </span>
            </button>

            {/* Online indicator */}
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <span className="text-xs text-emerald-400 font-medium">Online</span>
            </div>
          </div>
        </div>

        {/* Student mode banner */}
        <AnimatePresence>
          {isStudentMode && (
            <motion.div
              key="student-banner"
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              transition={{ duration: 0.3 }}
              className="mb-4 px-4 py-3 rounded-xl bg-violet-500/10 border border-violet-500/30 text-xs text-violet-300 flex items-center gap-2 z-10"
            >
              <GraduationCap size={14} className="shrink-0" />
              <span>
                <strong>Reverse Feynman Mode</strong> — explain a physics concept as clearly
                as you can. Feynman will evaluate your explanation, flag jargon, and score you on
                simplicity &amp; clarity out of 10.
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto mb-6 px-2 md:px-6 z-10 custom-scrollbar space-y-6">
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.4, type: "spring", bounce: 0.3 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`flex max-w-[85%] md:max-w-[75%] ${
                    msg.role === "user" ? "flex-row-reverse" : "flex-row"
                  } gap-4 items-end`}
                >
                  {/* Avatar */}
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-md ${
                      msg.role === "user"
                        ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                        : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    }`}
                  >
                    {msg.role === "user" ? <User size={16} /> : <Brain size={16} />}
                  </div>

                  {/* Bubble */}
                  <div className="flex flex-col gap-1">
                    <div
                      className={`px-5 py-3.5 rounded-2xl shadow-sm text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "bg-indigo-600/90 text-white rounded-br-sm backdrop-blur-md"
                          : "glass-panel text-gray-200 rounded-bl-sm"
                      }`}
                    >
                                              <div className="prose prose-invert max-w-none text-sm md:text-base leading-relaxed">
                          <ReactMarkdown
                            remarkPlugins={[remarkMath]}
                            rehypePlugins={[rehypeKatex]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                    </div>

                    {/* ⚡ Cached badge */}
                    {msg.role === "assistant" && msg.is_cached && (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className={`
                          self-start flex items-center gap-1 px-2 py-0.5 rounded-full
                          text-[10px] font-medium tracking-wide
                          bg-amber-500/10 border border-amber-500/25 text-amber-400
                        `}
                      >
                        ⚡ Cached
                      </motion.span>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {isLoading && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start"
            >
              <div className="flex max-w-[85%] flex-row gap-4 items-end">
                <div className="w-8 h-8 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 flex items-center justify-center shrink-0">
                  <Brain size={16} />
                </div>
                <div className="px-5 py-3 rounded-2xl glass-panel text-gray-300 rounded-bl-sm flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin text-cyan-400" />
                  <span className="text-xs">Feynman is thinking...</span>
                </div>
              </div>
            </motion.div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div
          className={`glass p-2 rounded-2xl z-10 shadow-xl border transition-colors duration-300 ${
            isStudentMode ? "border-violet-500/30" : "border-white/10"
          }`}
        >
          {/* Mode toggle sits above the text input */}
          <div className="flex items-center justify-between px-2 pb-2 pt-1">
            <ModeToggle mode={chatMode} onChange={setChatMode} />
            <span className="text-[10px] text-gray-600 hidden sm:block">
              {isStudentMode
                ? "Explain a concept — Feynman will evaluate you"
                : "Ask Feynman anything about physics"}
            </span>
          </div>

          <form onSubmit={handleSend} className="flex items-center gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={
                isListening
                  ? "Listening… speak now"
                  : isStudentMode
                    ? "Explain a physics concept in your own words…"
                    : "Ask Feynman a physics question…"
              }
              className="flex-1 bg-transparent border-0 focus-visible:ring-0 text-white placeholder:text-gray-500 h-12 text-base px-4"
              disabled={isLoading}
            />

            {/* Mic button */}
            <button
              type="button"
              onClick={toggleListening}
              disabled={isLoading}
              title={isListening ? "Stop listening" : "Speak your question"}
              className={`
                rounded-xl h-10 w-10 flex items-center justify-center transition-all duration-200 shrink-0
                ${isListening
                  ? "bg-red-500/90 hover:bg-red-400 text-white shadow-[0_0_12px_rgba(239,68,68,0.5)] animate-pulse"
                  : "bg-white/10 hover:bg-white/20 text-gray-400 hover:text-white"
                }
                disabled:opacity-40 disabled:cursor-not-allowed
              `}
            >
              {isListening ? <MicOff size={17} /> : <Mic size={17} />}
            </button>

            {/* Send button */}
            <Button
              type="submit"
              size="icon"
              disabled={!inputValue.trim() || isLoading}
              className={`
                rounded-xl h-10 w-10 text-white transition-all shadow-md mr-1 shrink-0
                ${isStudentMode
                  ? "bg-violet-600 hover:bg-violet-500"
                  : "bg-blue-600 hover:bg-blue-500"
                }
              `}
            >
              <Send size={18} className={isLoading ? "opacity-50" : ""} />
            </Button>
          </form>
        </div>

      </div>
    </div>
  );
}
