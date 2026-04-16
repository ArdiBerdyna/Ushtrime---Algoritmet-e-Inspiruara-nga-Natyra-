from scheduler.greedy_scheduler import GreedyScheduler
from models.schedule import Schedule
from models.solution import Solution

class UpperBoundGreedy(GreedyScheduler):
    def __init__(self, instance_data, fixed_duration=30, include_all_preferences=True):
        super().__init__(instance_data)
        self.fixed_duration = fixed_duration
        self.include_all_preferences = include_all_preferences

    def compute_theoretical_upper_bound(self) -> float:
        base_score = sum(p.score for ch in self.instance_data.channels for p in ch.programs)
        bonus_score = 0.0

        if self.include_all_preferences:
            bonus_score += sum(pref.bonus for pref in self.instance_data.time_preferences)

        return float(base_score + bonus_score)

    def generate_solution(self) -> Solution:
        print("[INFO] Running Relaxed Upper Bound Scheduler (time-aware bonus applied)...")

        opening = self.instance_data.opening_time
        closing = self.instance_data.closing_time
        total_score = 0.0
        relaxed_schedules = []

        current_time = opening

        all_programs = [
            (p, ch) for ch in self.instance_data.channels for p in ch.programs
        ]

        all_programs.sort(key=lambda x: x[0].score, reverse=True)

        for prog, ch in all_programs:
            if current_time >= closing:
                break

            start = current_time
            end = min(start + self.fixed_duration, closing)
            current_time = end

            fitness = prog.score

            for pref in self.instance_data.time_preferences:
                if (
                    pref.preferred_genre.lower() == prog.genre.lower()
                    and not (end <= pref.start or start >= pref.end)
                ):
                    fitness += pref.bonus

            relaxed_schedules.append(
                Schedule(
                    program_id=prog.program_id,
                    channel_id=ch.channel_id,
                    start=start,
                    end=end,
                    fitness=fitness,
                    unique_program_id=prog.unique_id,
                )
            )

            total_score += fitness

        print(f"[INFO] Relaxed schedule generated — total score: {total_score:.2f}")
        return Solution(scheduled_programs=relaxed_schedules, total_score=total_score)