"use client";

import Header from "@/components/Header";
import InputBar from "@/components/InputBar";
import MessageArea from "@/components/MessageArea";
import React, { useState } from "react";

interface Message {
  id: number;
  content: string;
  isUser: boolean;
  type: string;
  isLoading?: boolean;
}

const Home = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      content: "Hi there, how can I help you?",
      isUser: false,
      type: "message",
    },
  ]);

  const [currentMessage, setCurrentMessage] = useState("");
  const [checkpointId, setCheckpointId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMessage.trim()) return;

    const newMessageId =
      messages.length > 0 ? Math.max(...messages.map((m) => m.id)) + 1 : 1;

    // Store user message
    setMessages((prev) => [
      ...prev,
      {
        id: newMessageId,
        content: currentMessage,
        isUser: true,
        type: "message",
      },
    ]);

    const userInput = currentMessage;
    setCurrentMessage("");

    const aiResponseId = newMessageId + 1;

    // Placeholder bot message
    setMessages((prev) => [
      ...prev,
      {
        id: aiResponseId,
        content: "",
        isUser: false,
        type: "message",
        isLoading: true,
      },
    ]);

    try {
      let url = `http://127.0.0.1:8000/chat_stream/${encodeURIComponent(
        userInput
      )}`;

      if (checkpointId) url += `?checkpoint_id=${encodeURIComponent(checkpointId)}`;

      const eventSource = new EventSource(url);

      let streamedContent = "";

      eventSource.onmessage = (event) => {
        if (!event.data || event.data.trim() === "") return;

        let data: any;

        try {
          data = JSON.parse(event.data);
        } catch (err) {
          console.warn("Skipping non-JSON SSE chunk:", event.data);
          return;
        }

        if (data.type === "checkpoint") {
          setCheckpointId(data.checkpoint_id);
        }

        if (data.type === "content") {
          streamedContent += data.content;

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === aiResponseId
                ? { ...msg, content: streamedContent, isLoading: false }
                : msg
            )
          );
        }

        if (data.type === "end") {
          eventSource.close();
        }
      };

      eventSource.onerror = () => {
        console.error("EventSource connection failed");

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiResponseId
              ? {
                  ...msg,
                  content:
                    "Sorry, connection failed. Please try again later.",
                  isLoading: false,
                }
              : msg
          )
        );

        eventSource.close();
      };
    } catch (error) {
      console.error("Error setting up SSE:", error);
    }
  };

  return (
    <div className="flex justify-center bg-gray-100 min-h-screen py-8 px-4">
      <div className="w-[70%] bg-white flex flex-col rounded-xl shadow-lg border border-gray-100 overflow-hidden h-[90vh]">
        <Header />
        <MessageArea messages={messages} />
        <InputBar
          currentMessage={currentMessage}
          setCurrentMessage={setCurrentMessage}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  );
};

export default Home;
