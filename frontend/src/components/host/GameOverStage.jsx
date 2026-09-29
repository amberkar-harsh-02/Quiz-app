import { Button } from '../ui';

export default function GameOverStage({ saved, onDashboard, onAnalytics }) {
  return (
    <div className="flex flex-grow flex-col items-center justify-center text-center motion-safe:animate-rise">
      <h1 className="mb-4 text-7xl font-bold tracking-tight">Game Over!</h1>
      <p className="mb-12 text-2xl text-white/70">
        {saved ? 'Scores have been saved. You can review them in Analytics.' : 'No questions were played, so nothing was saved.'}
      </p>
      <div className="flex gap-4">
        <Button size="lg" onClick={onDashboard} className="bg-white !text-stage hover:bg-white/90">Return to Dashboard</Button>
        {saved && <Button variant="stage" size="lg" onClick={onAnalytics}>View Analytics</Button>}
      </div>
    </div>
  );
}
