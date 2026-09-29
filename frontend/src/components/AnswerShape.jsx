import { answerFor } from '../answers';

const PATHS = {
  triangle: <polygon points="12,3 22,21 2,21" />,
  diamond: <polygon points="12,2 22,12 12,22 2,12" />,
  circle: <circle cx="12" cy="12" r="10" />,
  square: <rect x="3" y="3" width="18" height="18" />,
};

// Solid shape for an answer color, drawn in currentColor
export default function AnswerShape({ color, className = 'h-6 w-6' }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      {PATHS[answerFor(color).shape]}
    </svg>
  );
}
