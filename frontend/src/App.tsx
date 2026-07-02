import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useMutation } from '@tanstack/react-query';
import { MessageSquare, Sparkles, RefreshCcw } from 'lucide-react';
import { postChat } from './services/api';
import { ChatMessage, ChatResponse, Recommendation } from './types';
import ChatLayout from './components/ChatLayout';
import EmptyState from './components/EmptyState';
import InputBar from './components/InputBar';
import LoadingIndicator from './components/LoadingIndicator';
import RecommendationCard from './components/RecommendationCard';
import ThemeToggle from './components/ThemeToggle';

const suggestedPrompts = [
  'Hiring a mid-professional SQL developer',
  'Compare SQL and Spring assessments',
  'Need a personality assessment for graduate hires',
  'Require an assessment under 30 minutes',
];

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [input, setInput] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  const mutation = useMutation<ChatResponse, Error, ChatMessage[]>({
    mutationFn: postChat,
    onError: () => {
      setErrorMessage('Unable to reach the backend. Please try again.');
    },
  });

  const isLoading = mutation.status === 'pending';

  const reply = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((item) => item.role === 'assistant');
    return latestAssistant?.content ?? '';
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) {
      return;
    }
    setErrorMessage('');
    const nextMessages: ChatMessage[] = [...messages, { role: 'user', content: input.trim() }];
    setMessages(nextMessages);
    setInput('');

    try {
      const response = await mutation.mutateAsync(nextMessages);
      setMessages((current) => [...current, { role: 'assistant', content: response.reply }]);
      setRecommendations(response.recommendations);
    } catch {
      setMessages((current) => [...current, { role: 'assistant', content: 'I was not able to complete your request. Please try again.' }]);
      setRecommendations([]);
    }
  };

  const handlePrompt = (prompt: string) => {
    setInput(prompt);
  };

  const clearConversation = () => {
    setMessages([]);
    setRecommendations([]);
    setErrorMessage('');
    setInput('');
  };

  const toggleTheme = () => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  };

  return (
    <div className={theme === 'dark' ? 'min-h-screen bg-slate-950 text-slate-100' : 'min-h-screen bg-slate-50 text-slate-950'}>
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <ChatLayout>
          <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">SHL assessment recommender</p>
            <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Grounded catalog recommendations</h1>
          </div>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>

        <div className="grid flex-1 gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-glass backdrop-blur-xl dark:border-slate-800/60 dark:bg-slate-950/80">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm text-slate-400">FastAPI backend · stateless chat · catalog-only retrieval</p>
                <p className="mt-1 text-sm text-slate-400">Server endpoint: <span className="font-mono text-slate-200">/chat</span></p>
              </div>
              <button
                type="button"
                onClick={clearConversation}
                className="inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/80 px-4 py-2 text-sm text-slate-100 transition hover:bg-slate-800"
              >
                <RefreshCcw className="h-4 w-4" />
                Clear
              </button>
            </div>

            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              {suggestedPrompts.map((prompt) => (
                <motion.button
                  key={prompt}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  type="button"
                  onClick={() => handlePrompt(prompt)}
                  className="rounded-2xl border border-slate-700/80 bg-slate-900/80 px-4 py-3 text-left text-sm text-slate-200 transition hover:border-cyan-400/80 hover:bg-slate-800"
                >
                  <div className="flex items-center gap-2 text-cyan-300"><Sparkles className="h-4 w-4" /> Suggested prompt</div>
                  <p className="mt-2 leading-6">{prompt}</p>
                </motion.button>
              ))}
            </div>

            <div className="mb-4 rounded-3xl border border-slate-700/70 bg-slate-950/80 p-4 shadow-inner shadow-slate-950/30">
              {messages.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="space-y-4">
                  {messages.map((message, index) => (
                    <div key={`${message.role}-${index}`} className={message.role === 'user' ? 'text-right' : 'text-left'}>
                      <div className={message.role === 'user' ? 'inline-flex items-center justify-end rounded-3xl bg-cyan-500/15 px-4 py-3 text-slate-200' : 'inline-flex items-center rounded-3xl bg-slate-800 px-4 py-3 text-slate-100'}>
                        {message.role === 'assistant' ? <MessageSquare className="mr-2 h-4 w-4 text-cyan-300" /> : null}
                        <span>{message.content}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-slate-700/70 bg-slate-900/80 p-4">
              <InputBar
                value={input}
                onChange={(value) => setInput(value)}
                onSubmit={sendMessage}
                disabled={isLoading}
              />
            </div>
            {errorMessage ? <p className="mt-3 text-sm text-rose-300">{errorMessage}</p> : null}
            {isLoading ? <LoadingIndicator /> : null}
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glass backdrop-blur-xl dark:border-slate-800/60 dark:bg-slate-950/80">
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-2xl bg-cyan-500/10 p-3 text-cyan-300">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">Recommendations</h2>
                <p className="text-sm text-slate-400">Powered by the provided SHL catalog.</p>
              </div>
            </div>

            {recommendations.length > 0 ? (
              <div className="space-y-4">
                {recommendations.map((item) => (
                  <RecommendationCard key={item.url} item={item} />
                ))}
              </div>
            ) : (
              <div className="rounded-3xl border border-dashed border-slate-700/60 bg-slate-950/70 p-6 text-sm text-slate-400">
                {reply ? 'This conversation does not include a catalog shortlist yet.' : 'Send a query to receive grounded SHL recommendations.'}
              </div>
            )}
          </div>
        </div>
      </ChatLayout>
      </div>
    </div>
  );
}

export default App;
