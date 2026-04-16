import random
import math
import traceback
from typing import Optional, List
from numbers import Number

from models.instance_data import InstanceData
from models.solution import Solution
from scheduler.beam_search import BeamSearchScheduler


class BeamSearchSchedulerAdvanced:
    def __init__(
        self,
        instance_data: InstanceData,
        beam_width: int = 3,
        jump_cap: int = 30,
        backtrack_window: int = 10,
    ):
        self.instance_data = instance_data
        self.beam_width = beam_width
        self.jump_cap = jump_cap
        self.backtrack_window = backtrack_window

        self._restarts_run: int = 0
        self._best_score_history: List[float] = []
        self._last_seed: Optional[int] = None

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
        if not isinstance(self.backtrack_window, int) or self.backtrack_window <= 0:
            print(f"WARNING: backtrack_window was {self.backtrack_window!r}; forcing default=1.")
            self.backtrack_window = 1

    def _seed_random(self, seed: Optional[int] = None) -> int:
        if seed is None:
            seed = random.randint(0, 1_000_000)
        random.seed(seed)
        self._last_seed = seed
        return seed

    def _create_scheduler(self, dynamic_width: int) -> BeamSearchScheduler:
        # Defensive check
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
            print("WARNING: scheduler returned None solution; treating score as -inf.")
            return -float("inf")
        # Check attribute existence
        if not hasattr(solution, "total_score"):
            print("WARNING: solution has no attribute 'total_score'; treating score as -inf.")
            return -float("inf")
        score = getattr(solution, "total_score")
        if not isinstance(score, Number) or not math.isfinite(score):
            print(f"WARNING: solution.total_score is not a finite number ({score!r}); treating as -inf.")
            return -float("inf")
        return float(score)

    def _run_single_restart(self, restart_index: int, restarts: int) -> Optional[Solution]:
        try:
            seed = self._seed_random()
            dynamic_width = max(1, int(self.beam_width * random.uniform(0.8, 1.5)))
            print(f"[Restart {restart_index + 1}/{restarts}] Beam width = {dynamic_width}, Seed = {seed}")

            scheduler = self._create_scheduler(dynamic_width)

            solution = scheduler.generate_solution()

            if solution is None:
                print(f"WARNING: Restart {restart_index + 1} produced None solution.")
                return None

            score = self._safe_get_score(solution)
            if score == -float("inf"):
                print(f"WARNING: Restart {restart_index + 1} returned invalid score; ignoring result.")
                return None

            print(f"  → Restart {restart_index + 1} finished with score: {score}")
            return solution

        except Exception as exc:
            print(f"WARNING: Exception during restart {restart_index + 1}: {exc}")
            traceback.print_exc()
            return None

    def generate_solution(self, restarts: int = 3) -> Solution:
        if not isinstance(restarts, int) or restarts <= 0:
            print(f"WARNING: restarts was {restarts!r}; forcing restarts=1.")
            restarts = 1

        best_solution: Optional[Solution] = None
        best_score: float = -float("inf")
        self._restarts_run = 0
        self._best_score_history.clear()

        for r in range(restarts):
            self._restarts_run += 1
            solution = self._run_single_restart(r, restarts)

            if solution is None:
                continue

            score = self._safe_get_score(solution)

            self._best_score_history.append(score)

            if score > best_score:
                best_score = score
                best_solution = solution

        if best_solution is None:
            print("WARNING: All restarts failed to produce a valid solution. Returning a fallback Solution.")
            try:
                best_solution = Solution(scheduled_programs=[], total_score=-float("inf"))
            except Exception as exc:
                print("WARNING: Could not create fallback Solution instance. Re-raising exception.")
                raise RuntimeError("BeamSearchSchedulerAdvanced failed to produce any valid Solution") from exc

        print(f"\nBest solution after {self._restarts_run} restarts: {best_score}")
        return best_solution

    def get_last_seed(self) -> Optional[int]:
        return self._last_seed

    def get_restarts_run(self) -> int:
        return self._restarts_run

    def get_score_history(self) -> List[float]:
        return list(self._best_score_history)
