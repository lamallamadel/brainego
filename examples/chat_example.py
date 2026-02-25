#!/usr/bin/env python3
"""
Example: Interactive chat with Llama 3.3 via OpenAI-compatible API
"""

import requests
import json
from typing import List, Dict

API_URL = "http://localhost:8000/v1/chat/completions"


class ChatSession:
    def __init__(self, system_prompt: str = "You are a helpful AI assistant."):
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation history."""
        self.messages.append({"role": role, "content": content})
    
    def chat(self, user_input: str, temperature: float = 0.7, max_tokens: int = 500) -> str:
        """Send a message and get a response."""
        self.add_message("user", user_input)
        
        payload = {
            "model": "llama-3.3-8b-instruct",
            "messages": self.messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(API_URL, json=payload, timeout=300)
            response.raise_for_status()
            
            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"]
            
            self.add_message("assistant", assistant_message)
            
            return assistant_message
            
        except requests.exceptions.RequestException as e:
            return f"Error: {e}"


def main():
    print("=" * 60)
    print("Interactive Chat with Llama 3.3 8B Instruct")
    print("=" * 60)
    print("\nType 'quit' or 'exit' to end the conversation")
    print("Type 'clear' to start a new conversation")
    print("Type 'history' to see conversation history\n")
    
    session = ChatSession(
        system_prompt="You are a knowledgeable and helpful AI assistant. "
                     "Provide clear, concise, and accurate answers."
    )
    
    while True:
        try:
            user_input = input("\n🧑 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit"]:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == "clear":
                session = ChatSession()
                print("\n✨ Started new conversation")
                continue
            
            if user_input.lower() == "history":
                print("\n📜 Conversation History:")
                for i, msg in enumerate(session.messages[1:], 1):  # Skip system message
                    role = "🧑 You" if msg["role"] == "user" else "🤖 Assistant"
                    print(f"\n{role}: {msg['content']}")
                continue
            
            print("\n🤖 Assistant: ", end="", flush=True)
            response = session.chat(user_input)
            print(response)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
