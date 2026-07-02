import { ChatMessage } from '../types';

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  return (
    <div className={isUser ? 'text-right' : 'text-left'}>
      <div className={isUser ? 'inline-flex items-center justify-end rounded-3xl bg-cyan-500/15 px-4 py-3 text-slate-200' : 'inline-flex items-center rounded-3xl bg-slate-800 px-4 py-3 text-slate-100'}>
        <span>{message.content}</span>
      </div>
    </div>
  );
}
