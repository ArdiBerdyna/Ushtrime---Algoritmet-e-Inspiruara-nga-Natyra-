import argparse
import bisect
import json
import statistics
import time
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.channel import Channel
from models.instance_data import InstanceData
from models.program import Program
from models.schedule import Schedule
from models.solution import Solution
from parser.file_selector import select_file
from parser.parser import Parser
from utils.algorithm_utils import AlgorithmUtils
from utils.utils import Utils

class SolutionMethod2Tuned:
    """Genetic scheduler with guided initialization and configurable elite(top) size."""

    def __init__(
        self,
        instance_data: InstanceData,
        seed: int = 42,
        population_size: int = 24,
        generations: int = 25,
        elite_size: int = 2,
        mutation_rate: float = 0.08,
        crossover_rate: float = 0.9,
        gene_bonus_scale: float = 50.0,
        tournament_size: int = 3,
        run_time_limit: Optional[float] = None,
    ):
        self.instance_data = instance_data
        self.rng = random.Random(seed)
        self.population_size = max(6, population_size)
        self.generations = max(1, generations)
        self.elite_size = min(max(1, elite_size), self.population_size)
        self.mutation_rate = min(max(0.0, mutation_rate), 1.0)
        self.crossover_rate = min(max(0.0, crossover_rate), 1.0)
        self.gene_bonus_scale = gene_bonus_scale
        self.tournament_size = max(2, tournament_size)
        self.run_time_limit = run_time_limit

        self._all_programs = self._build_program_pool()
        self._program_starts = [program.start for _, program in self._all_programs]
        self._uid_to_gene_index = {
            program.unique_id: idx for idx, (_, program) in enumerate(self._all_programs)
        }
        self._chromosome_length = len(self._all_programs)

    def generate_solution(self) -> Solution:
        if self._chromosome_length == 0:
            return Solution(scheduled_programs=[], total_score=0)

        start_time = time.perf_counter()
        population = self._initial_population()
        evaluated = [self._evaluate_chromosome(chrom) for chrom in population]

        best_score, best_solution, best_chromosome = max(evaluated, key=lambda item: item[0])

        for _ in range(self.generations):
            if self._is_time_exceeded(start_time):
                break

            ranked = sorted(evaluated, key=lambda item: item[0], reverse=True)
            elites = [item[2][:] for item in ranked[:self.elite_size]]
            new_population = elites[:]

            while len(new_population) < self.population_size:
                if self._is_time_exceeded(start_time):
                    break

                parent_a = self._tournament_select(population, evaluated)
                parent_b = self._tournament_select(population, evaluated)
                child_a, child_b = self._crossover(parent_a, parent_b)
                self._mutate(child_a)
                self._mutate(child_b)

                new_population.append(child_a)
                if len(new_population) < self.population_size:
                    new_population.append(child_b)

            population = new_population
            evaluated = [self._evaluate_chromosome(chrom) for chrom in population]

            gen_best_score, gen_best_solution, gen_best_chromosome = max(evaluated, key=lambda item: item[0])
            if gen_best_score > best_score:
                best_score = gen_best_score
                best_solution = gen_best_solution
                best_chromosome = gen_best_chromosome[:]

        return best_solution

    def _initial_population(self) -> List[List[float]]:
        guided_count = max(1, self.population_size // 3)
        population = [self._guided_chromosome() for _ in range(guided_count)]
        while len(population) < self.population_size:
            population.append(self._random_chromosome())
        return population

    def _guided_chromosome(self) -> List[float]:
        """
        Build a guided (not fully random) chromosome:
        - favor high-score programs
        - favor programs that start earlier in the window
        - keep small noise for diversity
        """
        max_score = max((program.score for _, program in self._all_programs), default=1)
        span = max(1, self.instance_data.closing_time - self.instance_data.opening_time)

        chromosome: List[float] = []
        for _, program in self._all_programs:
            score_component = program.score / max_score
            time_component = 1.0 - ((program.start - self.instance_data.opening_time) / span)
            time_component = min(max(time_component, 0.0), 1.0)
            noise = self.rng.uniform(0.0, 0.15)
            gene = min(1.0, 0.75 * score_component + 0.20 * time_component + noise)
            chromosome.append(gene)
        return chromosome

    def _build_program_pool(self) -> List[Tuple[Channel, Program]]:
        pool: List[Tuple[Channel, Program]] = []
        for channel in self.instance_data.channels:
            for program in channel.programs:
                pool.append((channel, program))
        pool.sort(key=lambda cp: (cp[1].start, cp[1].end, -cp[1].score, cp[0].channel_id))
        return pool

    def _get_feasible_at_earliest_start(
        self,
        current_time: int,
        scheduled: List[Schedule],
    ) -> List[Tuple[Channel, Program]]:
        earliest: Optional[int] = None
        feasible: List[Tuple[Channel, Program]] = []
        start_idx = bisect.bisect_left(self._program_starts, current_time)

        for idx in range(start_idx, self._chromosome_length):
            channel, program = self._all_programs[idx]
            if earliest is not None and program.start > earliest:
                break
            if self._is_feasible(channel, program, current_time, scheduled):
                if earliest is None:
                    earliest = program.start
                feasible.append((channel, program))

        return feasible

    def _is_feasible(
        self,
        channel: Channel,
        program: Program,
        current_time: int,
        scheduled: List[Schedule],
    ) -> bool:
        if program.start < self.instance_data.opening_time:
            return False
        if program.end > self.instance_data.closing_time:
            return False

        duration = program.end - program.start
        if duration < self.instance_data.min_duration:
            return False
        if program.start < current_time:
            return False
        if scheduled and program.start < scheduled[-1].end:
            return False
        if scheduled and scheduled[-1].unique_program_id == program.unique_id:
            return False
        if not self._respects_priority_blocks(channel.channel_id, program):
            return False
        if not self._respects_genre_streak_limit(program.genre, scheduled):
            return False
        return True

    def _respects_priority_blocks(self, channel_id: int, program: Program) -> bool:
        for block in self.instance_data.priority_blocks:
            overlaps = program.start < block.end and program.end > block.start
            if overlaps and channel_id not in block.allowed_channels:
                return False
        return True

    def _respects_genre_streak_limit(self, new_genre: str, scheduled: List[Schedule]) -> bool:
        if not scheduled:
            return True

        streak = 0
        for item in reversed(scheduled):
            prog = Utils.get_program_by_unique_id(self.instance_data, item.unique_program_id)
            if prog is None or prog.genre != new_genre:
                break
            streak += 1
        return streak < self.instance_data.max_consecutive_genre

    def _pick_best_candidate(
        self,
        scheduled: List[Schedule],
        feasible: List[Tuple[Channel, Program]],
        chromosome: Optional[List[float]] = None,
    ) -> Tuple[Channel, Program, int]:
        best = None
        best_selection_score = float("-inf")

        for channel, program in feasible:
            true_fitness = self._compute_true_fitness(scheduled, channel, program)

            stickiness_bonus = 0
            if scheduled and scheduled[-1].channel_id == channel.channel_id:
                stickiness_bonus = 5

            gene_bonus = 0.0
            if chromosome is not None:
                gene_index = self._uid_to_gene_index[program.unique_id]
                gene_bonus = chromosome[gene_index] * self.gene_bonus_scale

            selection_score = true_fitness + stickiness_bonus + gene_bonus
            selection_score += self.rng.random() * 0.0001

            if selection_score > best_selection_score:
                best_selection_score = selection_score
                best = (channel, program, true_fitness)

        return best

    def _compute_true_fitness(self, scheduled: List[Schedule], channel: Channel, program: Program) -> int:
        score = 0
        score += program.score
        score += AlgorithmUtils.get_time_preference_bonus(self.instance_data, program, program.start)
        score += AlgorithmUtils.get_switch_penalty(scheduled, self.instance_data, channel)
        score += AlgorithmUtils.get_delay_penalty(scheduled, self.instance_data, program, program.start)
        score += AlgorithmUtils.get_early_termination_penalty(scheduled, self.instance_data, program, program.start)
        return int(score)

    def _decode_chromosome(self, chromosome: List[float]) -> Solution:
        current_time = self.instance_data.opening_time
        scheduled: List[Schedule] = []
        total_score = 0

        while current_time < self.instance_data.closing_time:
            feasible = self._get_feasible_at_earliest_start(current_time, scheduled)
            if not feasible:
                break

            chosen_channel, chosen_program, true_fitness = self._pick_best_candidate(
                scheduled,
                feasible,
                chromosome,
            )

            scheduled.append(
                Schedule(
                    program_id=chosen_program.program_id,
                    channel_id=chosen_channel.channel_id,
                    start=chosen_program.start,
                    end=chosen_program.end,
                    fitness=true_fitness,
                    unique_program_id=chosen_program.unique_id,
                )
            )
            total_score += true_fitness
            current_time = chosen_program.end

        return Solution(scheduled_programs=scheduled, total_score=total_score)

    def _evaluate_chromosome(self, chromosome: List[float]) -> Tuple[int, Solution, List[float]]:
        solution = self._decode_chromosome(chromosome)
        return solution.total_score, solution, chromosome

    def _random_chromosome(self) -> List[float]:
        return [self.rng.random() for _ in range(self._chromosome_length)]

    def _tournament_select(
        self,
        population: List[List[float]],
        evaluated: List[Tuple[int, Solution, List[float]]],
    ) -> List[float]:
        candidates = self.rng.sample(range(len(population)), k=min(self.tournament_size, len(population)))
        winner_idx = max(candidates, key=lambda idx: evaluated[idx][0])
        return population[winner_idx][:]

    def _crossover(self, parent_a: List[float], parent_b: List[float]) -> Tuple[List[float], List[float]]:
        if self.rng.random() >= self.crossover_rate:
            return parent_a[:], parent_b[:]

        child_a: List[float] = []
        child_b: List[float] = []
        for gene_a, gene_b in zip(parent_a, parent_b):
            if self.rng.random() < 0.5:
                child_a.append(gene_a)
                child_b.append(gene_b)
            else:
                child_a.append(gene_b)
                child_b.append(gene_a)
        return child_a, child_b

    def _mutate(self, chromosome: List[float]) -> None:
        for idx in range(len(chromosome)):
            if self.rng.random() < self.mutation_rate:
                chromosome[idx] = self.rng.random()

    def _is_time_exceeded(self, start_time: float) -> bool:
        if self.run_time_limit is None:
            return False
        return (time.perf_counter() - start_time) >= self.run_time_limit


OUTPUT_ALGO2_DIR = Path("output_algo2")


def _parse_grid(values: str) -> List[int]:
    parsed = [int(v.strip()) for v in values.split(",") if v.strip()]
    if not parsed:
        raise ValueError("Grid cannot be empty.")
    return parsed


def _save_solution_to_output_algo2(
    solution: Solution,
    *,
    filename: str,
) -> Path:
    """Writes one schedule JSON under output_algo2/ (tuner-only output location)."""
    OUTPUT_ALGO2_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_ALGO2_DIR / filename
    schedules = []
    for schedule in solution.scheduled_programs:
        schedules.append({
            "program_id": schedule.program_id,
            "channel_id": schedule.channel_id,
            "start": schedule.start,
            "end": schedule.end,
        })
    data = {"scheduled_programs": schedules}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return output_path


def _save_top_runs_for_instance(
    file_path: Path,
    scored_solutions: List[Tuple[int, Solution, int, int, int, int, int]],
    keep_top_n: int,
) -> int:
    """
    Save top N runs for one instance (by score) and remove old top files for that
    same instance so rerunning does not accumulate 20, 30, ... files.
    Tuple format: (score, solution, cfg_idx, run_idx, pop, gen, elite)
    """
    base_name = file_path.stem.replace("_input", "")
    OUTPUT_ALGO2_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in OUTPUT_ALGO2_DIR.glob(f"{base_name}_algo2_top*.json"):
        try:
            old_file.unlink()
        except OSError:
            pass

    ranked = sorted(scored_solutions, key=lambda item: item[0], reverse=True)[:keep_top_n]
    for rank, (score, solution, cfg_idx, run_idx, pop, gen, elite) in enumerate(ranked, start=1):
        filename = (
            f"{base_name}_algo2_top{rank:02d}_{score}_"
            f"cfg{cfg_idx:02d}_p{pop}_g{gen}_t{elite}_r{run_idx:02d}.json"
        )
        _save_solution_to_output_algo2(solution, filename=filename)
    return len(ranked)


def _run_single(
    instance: InstanceData,
    seed: int,
    population_size: int,
    generations: int,
    elite_size: int,
    mutation_rate: float,
    crossover_rate: float,
    run_time_limit: float,
) -> Solution:
    scheduler = SolutionMethod2Tuned(
        instance_data=instance,
        seed=seed,
        population_size=population_size,
        generations=generations,
        elite_size=elite_size,
        mutation_rate=mutation_rate,
        crossover_rate=crossover_rate,
        run_time_limit=run_time_limit,
    )
    return scheduler.generate_solution()


def run_parameter_search(
    input_dir: str,
    instances: int = 10,
    runs_per_instance: int = 10,
    max_runtime: float = 300.0,
    base_seed: int = 42,
    population_grid: Optional[List[int]] = None,
    generation_grid: Optional[List[int]] = None,
    elite_grid: Optional[List[int]] = None,
    mutation_rate: float = 0.08,
    crossover_rate: float = 0.9,
    instance_paths: Optional[List[Path]] = None,
) -> None:
    # Default grid reduced to 6 combinations for faster execution.
    population_grid = population_grid or [20, 30]
    generation_grid = generation_grid or [20, 30, 40]
    elite_grid = elite_grid or [2]

    if instance_paths is not None:
        files = [p.resolve() for p in instance_paths]
    else:
        files = sorted(Path(input_dir).glob("*.json"))[:instances]
    if not files:
        print(f"No JSON instances found in: {input_dir}")
        return

    configs: List[Tuple[int, int, int]] = []
    for pop in population_grid:
        for gen in generation_grid:
            for elite in elite_grid:
                if elite <= pop:
                    configs.append((pop, gen, elite))

    if not configs:
        print("No valid parameter combinations found.")
        return

    print(
        f"Running parameter search on {len(files)} instances, "
        f"{runs_per_instance} runs each, max runtime {max_runtime:.1f}s."
    )
    print(f"Configurations: {len(configs)} combinations")

    started = time.perf_counter()
    runs_done = 0
    total_runs = len(files) * runs_per_instance * len(configs)
    best_overall = None
    best_score_overall = float("-inf")

    for file_idx, file_path in enumerate(files, start=1):
        parser = Parser(str(file_path))
        instance = parser.parse()
        Utils.set_current_instance(instance)
        print(f"\nInstance {file_idx}/{len(files)}: {file_path.name}")

        config_stats: List[Dict[str, float]] = []
        all_runs_scored: List[Tuple[int, Solution, int, int, int, int, int]] = []

        for cfg_idx, (pop, gen, elite) in enumerate(configs, start=1):
            scores: List[int] = []
            for run_idx in range(runs_per_instance):
                elapsed = time.perf_counter() - started
                if elapsed >= max_runtime:
                    print(f"\nTime limit reached ({elapsed:.2f}s). Stopping search.")
                    if all_runs_scored:
                        saved_partial = _save_top_runs_for_instance(
                            file_path=file_path,
                            scored_solutions=all_runs_scored,
                            keep_top_n=runs_per_instance,
                        )
                        print(f"[INFO] Saved top {saved_partial} partial outputs for {file_path.name}.")
                    return

                remaining_runs = max(1, total_runs - runs_done)
                remaining_time = max(0.1, max_runtime - elapsed)
                per_run_limit = max(0.1, remaining_time / remaining_runs)

                run_seed = (
                    base_seed
                    + file_idx * 1_000_000
                    + cfg_idx * 10_000
                    + run_idx
                )
                solution = _run_single(
                    instance=instance,
                    seed=run_seed,
                    population_size=pop,
                    generations=gen,
                    elite_size=elite,
                    mutation_rate=mutation_rate,
                    crossover_rate=crossover_rate,
                    run_time_limit=per_run_limit,
                )
                runs_done += 1
                scores.append(solution.total_score)
                all_runs_scored.append(
                    (int(solution.total_score), solution, cfg_idx, run_idx + 1, pop, gen, elite)
                )

                if solution.total_score > best_score_overall:
                    best_score_overall = solution.total_score
                    best_overall = (file_path, solution)

            avg_score = statistics.mean(scores)
            med_score = statistics.median(scores)
            config_stats.append(
                {
                    "population": pop,
                    "generations": gen,
                    "elite": elite,
                    "avg": avg_score,
                    "median": med_score,
                    "best": max(scores),
                }
            )
            print(
                f"  cfg {cfg_idx:02d}/{len(configs)} -> pop={pop}, gen={gen}, top={elite} | "
                f"scores={scores} | avg={avg_score:.1f} median={med_score:.1f} best={max(scores)}"
            )

        top_cfg = max(config_stats, key=lambda c: c["avg"])
        print(
            f"Best config for {file_path.name}: pop={int(top_cfg['population'])}, "
            f"gen={int(top_cfg['generations'])}, top={int(top_cfg['elite'])}, "
            f"avg={top_cfg['avg']:.1f}, best={int(top_cfg['best'])}"
        )

        saved_count = _save_top_runs_for_instance(
            file_path=file_path,
            scored_solutions=all_runs_scored,
            keep_top_n=runs_per_instance,
        )
        print(f"Saved top {saved_count} outputs for {file_path.name} under {OUTPUT_ALGO2_DIR}/")

    elapsed_total = time.perf_counter() - started
    print(
        f"\nParameter search completed: runs={runs_done}/{total_runs}, "
        f"elapsed={elapsed_total:.2f}s, best_score={best_score_overall}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Method 2 tuner with guided initialization. "
        "By default, opens a menu to pick one instance; use --all-instances for batch mode.",
    )
    parser.add_argument("--input-dir", default="data/input", help="Directory with instance JSON files")
    parser.add_argument(
        "--file",
        "-i",
        default=None,
        help="Run on this JSON file only (no interactive menu)",
    )
    parser.add_argument(
        "--all-instances",
        action="store_true",
        help="Run on multiple instances: first N files from input-dir (see --instances)",
    )
    parser.add_argument("--instances", type=int, default=10, help="With --all-instances: max number of files")
    parser.add_argument("--runs", type=int, default=10, help="Runs per config per instance (default: 10)")
    parser.add_argument("--max-runtime", type=float, default=300.0, help="Total runtime limit in seconds")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    parser.add_argument("--population-grid", type=str, default="20,30", help="Comma-separated population list")
    parser.add_argument("--generation-grid", type=str, default="20,30,40", help="Comma-separated generations list")
    parser.add_argument("--elite-grid", type=str, default="2", help="Comma-separated top/elite list")
    parser.add_argument("--mutation-rate", type=float, default=0.08, help="Mutation rate")
    parser.add_argument("--crossover-rate", type=float, default=0.9, help="Crossover rate")
    args = parser.parse_args()

    chosen_paths: Optional[List[Path]] = None
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"File not found: {path}")
            return
        chosen_paths = [path]
    elif args.all_instances:
        chosen_paths = None
    else:
        selected = select_file(args.input_dir)
        chosen_paths = [Path(selected)]

    run_parameter_search(
        input_dir=args.input_dir,
        instances=args.instances,
        runs_per_instance=args.runs,
        max_runtime=args.max_runtime,
        base_seed=args.seed,
        population_grid=_parse_grid(args.population_grid),
        generation_grid=_parse_grid(args.generation_grid),
        elite_grid=_parse_grid(args.elite_grid),
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        instance_paths=chosen_paths,
    )


if __name__ == "__main__":
    main()
