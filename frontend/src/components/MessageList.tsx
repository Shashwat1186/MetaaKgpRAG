import { useState, useEffect } from 'react';
import type { Message } from '../api/client';

// Simple markdown-like renderer for assistant messages
function renderContent(text: string) {
  // Bold
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code style="background:#1e1e1e;padding:1px 5px;border-radius:4px;font-family:monospace;font-size:12px">$1</code>');
  // Newlines
  text = text.replace(/\n/g, '<br/>');
  // Citations [1] -> <sup class="citation"><a href="#">[1]</a></sup>
  text = text.replace(/\[(\d+)\]/g, '<sup style="color:var(--accent);margin:0 2px;"><a href="#" title="Source $1" style="text-decoration:none">[$1]</a></sup>');
  return text;
}

const IconCopy = () => (
  <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
  </svg>
);

const IconRefresh = () => (
  <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
    <path d="M21 2v6h-6M3 12a9 9 0 0115-6.7L21 8M3 22v-6h6M21 12a9 9 0 01-15 6.7L3 16"/>
  </svg>
);

function AssistantMessageBubble({ msg, onRegenerate, isLatest }: { msg: Message, onRegenerate?: () => void, isLatest: boolean }) {
  const [displayedContent, setDisplayedContent] = useState('');
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    if (!isLatest) {
      setDisplayedContent(msg.content);
      return;
    }
    // Simulate streaming
    setDisplayedContent('');
    let i = 0;
    const interval = setInterval(() => {
      setDisplayedContent(() => {
        const next = msg.content.slice(0, i + 3);
        i += 3;
        if (i >= msg.content.length) clearInterval(interval);
        return next;
      });
    }, 20);
    return () => clearInterval(interval);
  }, [msg.content, isLatest]);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div style={{ width: '100%' }}>
      <div
        className="message-bubble"
        dangerouslySetInnerHTML={{ __html: renderContent(displayedContent) }}
      />
      <div className="message-actions">
        <button className="action-btn" onClick={handleCopy} aria-label="Copy message">
          <IconCopy /> {isCopied ? 'Copied!' : 'Copy'}
        </button>
        {onRegenerate && (
          <button className="action-btn" onClick={onRegenerate} aria-label="Regenerate response">
            <IconRefresh /> Regenerate
          </button>
        )}
      </div>
    </div>
  );
}

interface Props {
  messages: Message[];
  isThinking: boolean;
  onRegenerate?: (msgId: string) => void;
}

export default function MessageList({ messages, isThinking, onRegenerate }: Props) {
  return (
    <div className="messages-list">
      {messages.map((msg, idx) => {
        const isLatestAssistant = msg.role === 'assistant' && idx === messages.length - 1;
        return (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="message-role">
              {msg.role === 'user' ? 'You' : 'GraphMind'}
            </div>
            {msg.role === 'assistant' ? (
              <AssistantMessageBubble 
                msg={msg} 
                onRegenerate={onRegenerate ? () => onRegenerate(msg.id) : undefined}
                isLatest={isLatestAssistant}
              />
            ) : (
              <div className="message-bubble">
                {msg.content}
              </div>
            )}
          </div>
        );
      })}

      {isThinking && (
        <div className="message assistant">
          <div className="message-role">GraphMind</div>
          <div className="thinking-bubble">
            <div className="thinking-dots">
              <div className="thinking-dot" />
              <div className="thinking-dot" />
              <div className="thinking-dot" />
            </div>
            Searching knowledge base…
          </div>
        </div>
      )}
    </div>
  );
}
