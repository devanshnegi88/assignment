export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface Recommendation {
  name: string;
  url: string;
  test_type: string;
}

export interface ChatResponse {
  reply: string;
  recommendations: Recommendation[];
  end_of_conversation: boolean;
}
