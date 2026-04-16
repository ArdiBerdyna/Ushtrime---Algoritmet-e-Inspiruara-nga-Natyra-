import math
import traceback
import time
from typing import Optional, List, Tuple
from numbers import Number

from models.instance_data import InstanceData
from models.solution import Solution
from scheduler.beam_search import BeamSearchScheduler
from models.schedule import Schedule as ScheduleModel
from models.schedule import Schedule
from utils.utils import Utils
from utils.scheduler_utils import SchedulerUtils
from validator.validator import Validator
from utils.algorithm_utils import AlgorithmUtils


class BeyondDynamicBeamSearchSchedulerAdvanced:
    def __init__(
        self,
        instance_data: InstanceData,
        beam_width: int = 3,
        jump_cap: int = 30,
        backtrack_window: int = 10,
        iterative_deepening: bool = True,
        max_beam_multiplier: int = 3,
        base_depth: int = 1,
        max_depth: int = 2,
        stagnation_delta: float = 0.5,
        restarts_min: int = 2,
        restarts_max: int = 8,
        local_search_passes: int = 2,
        enable_logging: bool = False,
        log_path: Optional[str] = None,
    ):
        self.instance_data = instance_data
        self.beam_width = max(1, int(beam_width))
        self.jump_cap = max(1, int(jump_cap))
        self.backtrack_window = max(0, int(backtrack_window))

        self.iterative_deepening = bool(iterative_deepening)
        self.max_beam_multiplier = max(1, int(max_beam_multiplier))
        self.base_depth = max(1, int(base_depth))
        self.max_depth = max(1, int(max_depth))

        self.stagnation_delta = float(stagnation_delta)
        self.restarts_min = max(1, int(restarts_min))
        self.restarts_max = max(self.restarts_min, int(restarts_max))

        self.local_search_passes = max(0, int(local_search_passes))

        self.iteration_limit = None

        self.enable_logging = bool(enable_logging)
        self.log_path = log_path

        self._restarts_run: int = 0
        self._best_score_history: List[float] = []
        self._last_seed: Optional[int] = None
        self._prev_restart_best: Optional[float] = None

        self._validate_constructor_params()

    def _validate_constructor_params(self) -> None:
        if self.instance_data is None:
            print("WARNING: instance_data is None. Behavior undefined; proceed with caution.")
        if not isinstance(self.beam_width, int) or self.beam_width <= 0:
            print(f"WARNING: beam_width was {self.beam_width!r}; forcing default=1.")
            self.beam_width = 1
        if not isinstance(self.jump_cap, int) or self.jump_cap <= 0:
            print(f"WARNING: jump_cap was {self.jump_cap!r}; forcing default=1.")
            self.jump_cap = 1
        if not isinstance(self.backtrack_window, int):
            print(f"WARNING: backtrack_window was {self.backtrack_window!r}; forcing default=0.")
            self.backtrack_window = 0
        if self.backtrack_window < 0:
            self.backtrack_window = 0

    def _create_scheduler(self, dynamic_width: int) -> BeamSearchScheduler:
        if not isinstance(dynamic_width, int) or dynamic_width <= 0:
            print(f"WARNING: dynamic_width invalid ({dynamic_width!r}), using 1.")
            dynamic_width = 1
        return BeamSearchScheduler(
            instance_data=self.instance_data,
            beam_width=dynamic_width,
            jump_cap=self.jump_cap,
            backtrack_window=self.backtrack_window,
        )

    def _safe_get_score(self, solution: Optional[Solution]) -> float:
        if solution is None:
            return -float("inf")
        if not hasattr(solution, "total_score"):
            return -float("inf")
        score = getattr(solution, "total_score")
        if not isinstance(score, Number) or not math.isfinite(score):
            return -float("inf")
        return float(score)

    def _dynamic_beam_adjustment(self, prev_score: Optional[float], current_score: float, current_width: int) -> int:
        if prev_score is None:
            return current_width
        if current_score <= prev_score + self.stagnation_delta:
            new_width = min(current_width * 2, int(self.beam_width * self.max_beam_multiplier))
        else:
            new_width = max(self.beam_width, int(current_width // 2))
        return max(1, int(new_width))

    def _detect_stagnation(self) -> bool:
        if len(self._best_score_history) < 2:
            return False
        return self._best_score_history[-1] <= self._best_score_history[-2] + self.stagnation_delta

    def _apply_adaptive_restart_policy(self):
        if self._detect_stagnation():
            self.jump_cap = min(self.jump_cap + 10, max(60, self.jump_cap * 2))
            self.beam_width = min(int(self.beam_width * 2), int(self.beam_width * self.max_beam_multiplier))
            print(f"[AdaptiveRestart] Stagnation detected, new jump_cap={self.jump_cap}, beam_width={self.beam_width}")

    def _refill_window(self, prefix: List[Schedule], window: int, trials: int = 1) -> Tuple[List[Schedule], int]:
        temp_sched = prefix.copy()
        local_beam = max(1, min(self.beam_width, 6))
        bs = self._create_scheduler(local_beam)

        fake_tail = [
            ScheduleModel(program_id="_pad", channel_id=-1, start=0, end=0, fitness=0, unique_program_id="_pad")
            for _ in range(window)
        ]
        base = temp_sched + fake_tail
        new_sched, new_score = bs._backtrack_improve(base, bs._score_full_schedule(base), window=window)
        return new_sched[: len(prefix) + window], int(new_score)

    def _enhanced_backtrack(self, scheduled: List[Schedule], total_score: int, max_trials: int = 6) -> Tuple[List[Schedule], int]:
        n = len(scheduled)
        if n == 0 or self.backtrack_window <= 0:
            return scheduled, total_score

        best_sched = scheduled
        best_score = total_score
        trials_used = 0
        max_trials = max(1, max_trials)

        W = min(self.backtrack_window, n)
        for window in range(1, W + 1):
            if trials_used >= max_trials:
                break
            last_start = n - window
            steps = min(last_start + 1, max_trials - trials_used)
            step_size = max(1, (last_start + 1) // max(1, steps))
            for start_idx in range(0, last_start + 1, step_size):
                prefix = scheduled[:start_idx]
                try:
                    candidate, _ = self._refill_window(prefix, window, trials=1)
                except Exception:
                    trials_used += 1
                    if trials_used >= max_trials:
                        break
                    continue
                tail = scheduled[start_idx + window :]
                full_candidate = candidate + tail

                if not self._respects_genre_limit(full_candidate):
                    trials_used += 1
                    if trials_used >= max_trials:
                        break
                    continue

                score_full = self._score_full_schedule(full_candidate)
                if score_full > best_score:
                    best_score = score_full
                    best_sched = full_candidate
                trials_used += 1
                if trials_used >= max_trials:
                    break

        return best_sched, int(best_score)

    def _local_search_replace(self, sched: List[Schedule], deadline: Optional[float] = None) -> Tuple[List[Schedule], int]:
        best_sched = sched
        best_score = self._score_full_schedule(sched)

        for idx in range(len(sched)):
            if deadline and time.time() > deadline:
                break
            prefix = best_sched[:idx]
            start_time = best_sched[idx].start
            for ch_idx, ch in enumerate(self.instance_data.channels):
                if deadline and time.time() > deadline:
                    break
                prog = Utils.get_channel_program_by_time(ch, start_time)
                if not prog:
                    continue
                if getattr(prog, "unique_id", None) == getattr(best_sched[idx], "unique_program_id", None):
                    continue

                try:
                    candidate = prefix.copy()
                    new_model = ScheduleModel(
                        program_id=prog.program_id,
                        channel_id=ch.channel_id,
                        start=prog.start,
                        end=prog.end,
                        fitness=int(
                            getattr(prog, "score", 0)
                            + AlgorithmUtils.get_time_preference_bonus(self.instance_data, prog, start_time)
                            + AlgorithmUtils.get_switch_penalty(prefix, self.instance_data, ch)
                            + AlgorithmUtils.get_delay_penalty(prefix, self.instance_data, prog, start_time)
                            + AlgorithmUtils.get_early_termination_penalty(prefix, self.instance_data, prog, start_time)
                        ),
                        unique_program_id=getattr(prog, "unique_id", prog.program_id),
                    )
                    candidate.append(new_model)
                    candidate.extend(best_sched[idx + 1 :])

                    if not Validator.is_channel_valid(prefix, self.instance_data, ch_idx, start_time):
                        continue

                    if not self._respects_genre_limit(candidate):
                        continue

                    score_candidate = self._score_full_schedule(candidate)
                    if score_candidate > best_score:
                        best_score = score_candidate
                        best_sched = candidate
                        break
                except Exception:
                    continue

        return best_sched, int(best_score)

    def _local_search_swap(self, sched: List[Schedule], deadline: Optional[float] = None) -> Tuple[List[Schedule], int]:
        best_sched = sched
        best_score = self._score_full_schedule(sched)
        n = len(sched)
        for i in range(n):
            if deadline and time.time() > deadline:
                break
            for j in range(i + 1, n):
                if deadline and time.time() > deadline:
                    break
                candidate = best_sched.copy()
                candidate[i], candidate[j] = candidate[j], candidate[i]
                ok = True
                for k in range(1, len(candidate)):
                    if candidate[k].start < candidate[k - 1].end:
                        ok = False
                        break
                if not ok:
                    continue

                if not self._respects_genre_limit(candidate):
                    continue

                score_candidate = self._score_full_schedule(candidate)
                if score_candidate > best_score:
                    best_score = score_candidate
                    best_sched = candidate
                    return best_sched, int(best_score)
        return best_sched, int(best_score)

    def _apply_local_search(self, best_solution: Solution, deadline: Optional[float] = None) -> Solution:
        best_sched = best_solution.scheduled_programs
        best_score = int(best_solution.total_score)
        for _ in range(self.local_search_passes):
            if deadline and time.time() > deadline:
                break
            cand_sched, cand_score = self._local_search_replace(best_sched, deadline)
            if cand_score > best_score:
                best_sched, best_score = cand_sched, cand_score
                continue
            cand_sched, cand_score = self._local_search_swap(best_sched, deadline)
            if cand_score > best_score:
                best_sched, best_score = cand_sched, cand_score
                continue
            break
        return Solution(scheduled_programs=best_sched, total_score=int(best_score))

    def generate_solution(self, restarts: int = 3) -> Solution:
        return self.generate_solution_with_time(restarts=restarts, time_limit=None)

    def generate_solution_with_time(self, restarts: int = 3, time_limit: Optional[float] = None) -> Solution:
        if not isinstance(restarts, int) or restarts <= 0:
            restarts = 1
        restarts = max(self.restarts_min, min(restarts, self.restarts_max))

        best_solution: Optional[Solution] = None
        best_score: float = -float("inf")
        self._restarts_run = 0
        self._best_score_history.clear()

        deadline = time.time() + time_limit if time_limit and time_limit > 0 else None

        current_dynamic_width = self.beam_width
        for r in range(restarts):
            self._restarts_run += 1

            dynamic_width = max(1, int(current_dynamic_width))
            print(f"[Restart {r + 1}/{restarts}] Beam width = {dynamic_width}")

            scheduler = self._create_scheduler(dynamic_width)
            try:
                candidate = scheduler.generate_solution()
            except Exception as exc:
                print(f"WARNING: Restart {r + 1} failed: {exc}")
                traceback.print_exc()
                candidate = None

            if candidate is None:
                continue

            if not self._respects_genre_limit(candidate.scheduled_programs):
                continue

            score = self._safe_get_score(candidate)
            if score == -float("inf"):
                continue

            self._best_score_history.append(score)
            if score > best_score:
                best_score = score
                best_solution = candidate

            current_dynamic_width = self._dynamic_beam_adjustment(
                self._prev_restart_best, score, current_dynamic_width
            )
            self._prev_restart_best = max(self._prev_restart_best or -float("-inf"), score)

            if self._detect_stagnation():
                self._apply_adaptive_restart_policy()

            if deadline and time.time() > deadline:
                print("[Main] time limit reached, stopping restarts loop.")
                break

        if best_solution is None:
            best_solution = Solution(scheduled_programs=[], total_score=0)
            best_score = 0

        print(f"\nBest solution after {self._restarts_run} restarts: {best_score}")

        if self.iterative_deepening and self.max_beam_multiplier > 1:
            for mult in range(2, self.max_beam_multiplier + 1):
                if deadline and time.time() > deadline:
                    print("[Iterative deepening] time limit reached, stopping iterative deepening.")
                    break
                dyn = max(1, int(self.beam_width * mult))
                print(f"[Iterative deepening] trying beam_width={dyn} (x{mult})")
                try:
                    sched = self._create_scheduler(dyn)
                    cand = sched.generate_solution()
                    if not self._respects_genre_limit(cand.scheduled_programs):
                        continue
                    sc = self._safe_get_score(cand)
                    if sc > best_score:
                        best_score = sc
                        best_solution = cand
                        print(f"  → Improved with beam_width={dyn}: {sc}")
                except Exception as exc:
                    print(f"WARNING: iterative deepening run with multiplier {mult} failed: {exc}")

        try:
            if best_solution and self.backtrack_window > 0:
                refined_sched, refined_score = self._enhanced_backtrack(
                    best_solution.scheduled_programs, int(best_solution.total_score), max_trials=8
                )
                if refined_score > best_score:
                    best_score = refined_score
                    best_solution = Solution(scheduled_programs=refined_sched, total_score=int(refined_score))
                    print(f"  [Enhanced backtrack] improved to: {refined_score}")
        except Exception as exc:
            print(f"WARNING: enhanced backtrack failed: {exc}")

        try:
            if best_solution and self.local_search_passes > 0:
                best_solution = self._apply_local_search(best_solution, deadline)
                best_score = int(best_solution.total_score)
        except Exception as exc:
            print(f"WARNING: local search phase failed: {exc}")

        print(f"Final best solution: {best_score}")

        if self.enable_logging and self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(f"seed=None,restarts={self._restarts_run},best_score={best_score}\n")
            except Exception:
                pass

        return best_solution

    def get_last_seed(self) -> Optional[int]:
        return None

    def get_restarts_run(self) -> int:
        return self._restarts_run

    def get_score_history(self) -> List[float]:
        return list(self._best_score_history)

    def _lookup_program(self, channel_id: int, start_time: int):
        try:
            for ch in getattr(self.instance_data, "channels", []):
                if getattr(ch, "channel_id", None) == channel_id:
                    return Utils.get_channel_program_by_time(ch, start_time)
        except Exception:
            pass
        return None

    def _get_program_genre(self, sched_entry: Schedule) -> Optional[str]:
        prog = self._lookup_program(getattr(sched_entry, "channel_id", None), getattr(sched_entry, "start", None))
        if prog is not None:
            g = getattr(prog, "genre", None) or getattr(prog, "category", None)
            if g:
                return str(g)
        g2 = getattr(sched_entry, "genre", None) or getattr(sched_entry, "category", None)
        return str(g2) if g2 else None

    def _get_max_consecutive_genre(self) -> int:
        return int(
            getattr(
                self.instance_data,
                "max_same_gen_R",
                getattr(
                    self.instance_data,
                    "max_consecutive_genre",
                    getattr(self.instance_data, "genre_diversity_limit", 2),
                ),
            )
        )

    def _respects_genre_limit(self, schedule: List[Schedule]) -> bool:
        limit = self._get_max_consecutive_genre()
        last_genre = None
        streak = 0
        for sch in schedule:
            g = self._get_program_genre(sch)
            if g is None:
                last_genre = None
                streak = 0
                continue
            if g == last_genre:
                streak += 1
            else:
                last_genre = g
                streak = 1
            if streak > limit:
                return False
        return True

    def _score_full_schedule(self, schedule: List[Schedule]) -> int:
        if not schedule:
            return 0

        if not self._respects_genre_limit(schedule):
            return -10**9

        overlap_penalty = int(getattr(self.instance_data, "overlap_penalty", 10_000))
        misorder_penalty = int(getattr(self.instance_data, "misorder_penalty", 1_000))
        genre_window = max(1, int(getattr(self.instance_data, "genre_window", 3)))
        genre_diversity_bonus = int(getattr(self.instance_data, "genre_diversity_bonus", 5))
        same_genre_chain_penalty = int(getattr(self.instance_data, "same_genre_chain_penalty", 8))

        total = 0
        recent_genres: List[Optional[str]] = []
        last_genre: Optional[str] = None
        same_genre_streak = 0

        for idx, sch in enumerate(schedule):
            total += getattr(sch, "fitness", 0)

            if idx > 0:
                prev = schedule[idx - 1]
                if getattr(sch, "start", 0) < getattr(prev, "end", 0):
                    if getattr(prev, "channel_id", None) == getattr(sch, "channel_id", None):
                        total -= overlap_penalty
                    else:
                        total -= misorder_penalty
                if getattr(prev, "channel_id", None) != getattr(sch, "channel_id", None):
                    total -= int(getattr(self.instance_data, "switch_penalty", 0))

            g = self._get_program_genre(sch)
            if g is not None:
                if g == last_genre:
                    same_genre_streak += 1
                    total -= same_genre_chain_penalty
                else:
                    same_genre_streak = 0
                    last_genre = g

                recent_genres.append(g)
                if len(recent_genres) > genre_window:
                    recent_genres.pop(0)
                unique_in_window = len(set([gg for gg in recent_genres if gg is not None]))
                total += genre_diversity_bonus * max(0, unique_in_window - 1)

        return int(total)
