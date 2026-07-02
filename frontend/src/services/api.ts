import { ChatMessage, ChatResponse } from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export async function postChat(messages: ChatMessage[]): Promise<ChatResponse> {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok) {
    throw new Error('Chat request failed');
  }

  return response.json();
}
