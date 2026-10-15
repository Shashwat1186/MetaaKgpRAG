const SUGGESTIONS = [
  {
    icon: '🍽️',
    title: 'Mess Rebate Rules',
    tag: 'HMC',
    body: 'What is the deadline and minimum leave required to claim HMC mess rebate?',
  },
  {
    icon: '📋',
    title: 'CDC Placements Tips',
    tag: 'CAREER',
    body: 'What are the most important preparation tips and strategies for CDC placements?',
  },
  {
    icon: '💼',
    title: 'CDC Internship Prep',
    tag: 'CAREER',
    body: 'Summarise key deadlines and resume verification rules for Autumn CDC.',
  },
  {
    icon: '🏥',
    title: 'Campus Essentials',
    tag: 'UTILITY',
    body: 'Find Central Library night timings and BC Roy hospital emergency contact info.',
  },
];

interface Props {
  onSuggest: (text: string) => void;
}

export default function WelcomeScreen({ onSuggest }: Props) {
  return (
    <div className="welcome">
      <div className="welcome-icon">G</div>
      <h1>Where knowledge meets <span className="highlight">KGP</span></h1>
      <p className="welcome-sub">
        Ask anything about courses, hall guidelines, CDC internships,<br />
        ERP procedures, or campus lore.
      </p>

      <div className="suggestions-grid">
        {SUGGESTIONS.map(s => (
          <button
            key={s.title}
            className="suggestion-card"
            onClick={() => onSuggest(s.body)}
          >
            <div className="suggestion-card-header">
              <div className="suggestion-card-title">
                {s.icon} {s.title}
              </div>
              <span className="suggestion-tag">{s.tag}</span>
            </div>
            <div className="suggestion-card-body">{s.body}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
