import { answerFor } from '../answers';

const SIZES = {
  sm: 'h-5 w-5 text-xs',
  md: 'h-7 w-7 text-sm',
  lg: 'h-10 w-10 text-lg',
  xl: 'h-16 w-16 text-3xl',
};

// Keycap with the answer's letter. `onColor` is for keys sitting on a tile that is already
// the answer's color, so the key reads as a raised cap instead of a second colored block.
export default function AnswerKey({ color, size = 'md', onColor = false }) {
  const answer = answerFor(color);
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-[28%] border-b-[3px] font-mono font-extrabold leading-none text-white ${SIZES[size]} ${
        onColor ? 'border-black/25 bg-white/20' : 'border-black/30'
      }`}
      style={onColor ? undefined : { backgroundColor: answer.bg }}
    >
      {answer.letter}
    </span>
  );
}
