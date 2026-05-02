import argparse
import bisect
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from models.channel import Channel
from models.instance_data import InstanceData
from models.program import Program
from models.schedule import Schedule
from models.solution import Solution
from parser.file_selector import select_file
from parser.parser import Parser
from serializer.serializer import SolutionSerializer, write_solution_json
from utils.algorithm_utils import AlgorithmUtils
from utils.utils import Utils


class SolutionMethod2:
    """
    Genetic algorithm based scheduler using crossover and mutation.

    Chromosome representation:
    - One floating-point weight per program in the global pool.
    - During decoding, at each earliest feasible start time, candidate program with the
      highest (true_fitness + weighted_gene_bonus) is selected.

    GA operators:
    - Crossover: uniform crossover.
    - Mutation: random-reset mutation on genes.

    Initial population (guided, not uniform random):
    - Genes biased toward higher ``program.score`` (normalized to ~[0.2, 0.9]).
    - One individual boosts genes for programs that appear in a greedy decode (all-zero genes).
    - Remaining slots mix prior weights with uniform noise for diversity.
    """

    def __init__(
        self,
        instance_data: InstanceData,
        seed: int = 42,
        population_size: int = 24,
        generations: int = 25,
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

            new_population = [best_chromosome[:]]

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
            tie_breaker = self.rng.random() * 0.0001
            selection_score += tie_breaker

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

    def _score_prior_genes(self) -> List[float]:
        """Map raw program scores to gene priors in ~[0.2, 0.9] for guided init."""
        if self._chromosome_length == 0:
            return []
        scores = [float(program.score) for _, program in self._all_programs]
        lo_s, hi_s = min(scores), max(scores)
        lo_g, hi_g = 0.2, 0.9
        if hi_s <= lo_s:
            mid = (lo_g + hi_g) / 2.0
            return [mid] * self._chromosome_length
        span = hi_s - lo_s
        return [lo_g + (s - lo_s) / span * (hi_g - lo_g) for s in scores]

    def _initial_population(self) -> List[List[float]]:
        """
        Seed population with score-aware priors and a greedy-schedule boost so early
        scores are not dominated by meaningless random tie-breaking.
        """
        n = self._chromosome_length
        prior = self._score_prior_genes()
        # Pure greedy selection path (gene_bonus = 0 for every program).
        greedy_schedule = self._decode_chromosome([0.0] * n)
        greedy_uids = {s.unique_program_id for s in greedy_schedule.scheduled_programs}

        greedy_boosted: List[float] = []
        for idx, (_, program) in enumerate(self._all_programs):
            g = prior[idx]
            if program.unique_id in greedy_uids:
                g = min(1.0, g + 0.18)
            greedy_boosted.append(g)

        population: List[List[float]] = [prior[:], greedy_boosted]
        while len(population) < self.population_size:
            alpha = self.rng.uniform(0.3, 0.65)
            chrom = [
                min(
                    1.0,
                    max(
                        0.0,
                        alpha * prior[i] + (1.0 - alpha) * self.rng.random(),
                    ),
                )
                for i in range(n)
            ]
            population.append(chrom)

        return population[: self.population_size]

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

        child_a = []
        child_b = []
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


def solution_method2(
    instance_data: InstanceData,
    seed: int = 42,
    population_size: int = 24,
    generations: int = 25,
    mutation_rate: float = 0.08,
    crossover_rate: float = 0.9,
    gene_bonus_scale: float = 50.0,
    tournament_size: int = 3,
    run_time_limit: Optional[float] = None,
) -> Solution:
    """Convenience entry point requested by assignment."""
    scheduler = SolutionMethod2(
        instance_data=instance_data,
        seed=seed,
        population_size=population_size,
        generations=generations,
        mutation_rate=mutation_rate,
        crossover_rate=crossover_rate,
        gene_bonus_scale=gene_bonus_scale,
        tournament_size=tournament_size,
        run_time_limit=run_time_limit,
    )
    return scheduler.generate_solution()


@dataclass(frozen=True)
class GAParameterSet:
    """Named GA hyperparameter bundle for reproducible experiments."""

    name: str
    population_size: int
    generations: int
    mutation_rate: float
    crossover_rate: float
    gene_bonus_scale: float
    tournament_size: int


# At least three distinct tuning regimes for assignment reporting.
PRESET_PARAMETER_SETS: Tuple[GAParameterSet, ...] = (
    GAParameterSet(
        name="A_balanced_default",
        population_size=24,
        generations=25,
        mutation_rate=0.08,
        crossover_rate=0.9,
        gene_bonus_scale=50.0,
        tournament_size=3,
    ),
    GAParameterSet(
        name="B_exploration_heavy",
        population_size=40,
        generations=40,
        mutation_rate=0.15,
        crossover_rate=0.85,
        gene_bonus_scale=80.0,
        tournament_size=5,
    ),
    GAParameterSet(
        name="C_exploitation_fast",
        population_size=16,
        generations=15,
        mutation_rate=0.05,
        crossover_rate=0.95,
        gene_bonus_scale=30.0,
        tournament_size=2,
    ),
)


def run_benchmark_10x10(
    input_dir: str,
    max_instances: int,
    runs_per_instance: int,
    max_runtime_seconds: float,
    base_seed: int,
    population_size: int,
    generations: int,
    mutation_rate: float,
    crossover_rate: float,
    gene_bonus_scale: float = 50.0,
    tournament_size: int = 3,
) -> None:
    input_path = Path(input_dir)
    files = sorted(input_path.glob("*.json"))[:max_instances]
    if not files:
        print(f"No input files found in: {input_dir}")
        return

    total_target_runs = len(files) * runs_per_instance
    completed_runs = 0
    total_start = time.perf_counter()
    stop = False

    print(
        f"Starting benchmark: instances={len(files)}, runs_per_instance={runs_per_instance}, "
        f"target_runs={total_target_runs}, max_runtime={max_runtime_seconds:.1f}s"
    )

    for file_idx, file_path in enumerate(files):
        if stop:
            break

        parser = Parser(str(file_path))
        instance = parser.parse()
        Utils.set_current_instance(instance)

        best_solution: Optional[Solution] = None
        best_score = float("-inf")

        for run_idx in range(runs_per_instance):
            elapsed = time.perf_counter() - total_start
            if elapsed >= max_runtime_seconds:
                stop = True
                print(
                    f"Time limit reached after {elapsed:.2f}s. "
                    f"Completed runs: {completed_runs}/{total_target_runs}"
                )
                break

            remaining_runs = max(1, total_target_runs - completed_runs)
            remaining_time = max(0.1, max_runtime_seconds - elapsed)
            run_time_limit = max(0.1, remaining_time / remaining_runs)

            run_seed = base_seed + (file_idx * 10_000) + run_idx
            scheduler = SolutionMethod2(
                instance_data=instance,
                seed=run_seed,
                population_size=population_size,
                generations=generations,
                mutation_rate=mutation_rate,
                crossover_rate=crossover_rate,
                gene_bonus_scale=gene_bonus_scale,
                tournament_size=tournament_size,
                run_time_limit=run_time_limit,
            )
            solution = scheduler.generate_solution()
            completed_runs += 1

            if solution.total_score > best_score:
                best_score = solution.total_score
                best_solution = solution

        if best_solution is not None:
            serializer = SolutionSerializer(input_file_path=str(file_path), algorithm_name="genetic_method2")
            serializer.serialize(best_solution)
            print(
                f"[{file_idx + 1}/{len(files)}] {file_path.name}: "
                f"best_score={best_solution.total_score}"
            )

    total_elapsed = time.perf_counter() - total_start
    print(
        f"Benchmark completed. Executed runs: {completed_runs}/{total_target_runs}. "
        f"Total time: {total_elapsed:.2f}s"
    )


# Default folder for 10 JSON outputs per (config, input) in parameter study mode.
DEFAULT_PARAMETER_STUDY_OUTPUT_DIR = Path("data/parameter_study_outputs")


def run_parameter_study(
    input_dir: str,
    max_instances: int,
    runs_per_instance: int,
    max_runtime_seconds: Optional[float],
    base_seed: int,
    parameter_sets: Tuple[GAParameterSet, ...] = PRESET_PARAMETER_SETS,
    output_root: Path = DEFAULT_PARAMETER_STUDY_OUTPUT_DIR,
    save_run_outputs: bool = True,
    instance_paths: Optional[Sequence[Path]] = None,
) -> Dict[str, object]:
    """
    For each parameter set, run ``runs_per_instance`` GA executions per instance file.
    When ``save_run_outputs`` is True, each run is written as a single file directly
    under ``output_root``: ``<input_stem>_score_<n>_run_<XX>_cfg_<i>.json`` (``cfg``
    indexes the parameter set 0.. so names stay unique across configs and runs).
    If ``instance_paths`` is set, only those JSON files are used (``max_instances`` /
    ``input_dir`` listing is ignored).
    If ``max_runtime_seconds`` is None, no global time limit is applied (each GA run
    uses ``run_time_limit=None``).
    Returns structured stats for reporting (and README).
    """
    if instance_paths is not None:
        files = [Path(p).resolve() for p in instance_paths]
    else:
        input_path = Path(input_dir)
        files = sorted(input_path.glob("*.json"))[:max_instances]
    if not files:
        print(f"No input files found in: {input_dir}")
        return {"configs": [], "instances": [], "per_config_instance": {}}

    total_runs_target = len(parameter_sets) * len(files) * runs_per_instance
    completed_runs = 0
    total_start = time.perf_counter()
    stop = False

    # scores[config_name][file_name] -> list of run scores
    all_scores: Dict[str, Dict[str, List[int]]] = {
        ps.name: {f.name: [] for f in files} for ps in parameter_sets
    }

    rt_display = "none" if max_runtime_seconds is None else f"{max_runtime_seconds:.1f}s"
    print(
        f"Parameter study: configs={len(parameter_sets)}, instances={len(files)}, "
        f"runs_per_instance={runs_per_instance}, target_runs={total_runs_target}, "
        f"max_runtime={rt_display}"
    )

    for cfg_idx, params in enumerate(parameter_sets):
        if stop:
            break
        for file_idx, file_path in enumerate(files):
            if stop:
                break

            parser = Parser(str(file_path))
            instance = parser.parse()
            Utils.set_current_instance(instance)

            for run_idx in range(runs_per_instance):
                elapsed = time.perf_counter() - total_start
                if max_runtime_seconds is not None and elapsed >= max_runtime_seconds:
                    stop = True
                    print(
                        f"Time limit reached after {elapsed:.2f}s. "
                        f"Completed runs: {completed_runs}/{total_runs_target}"
                    )
                    break

                if max_runtime_seconds is None:
                    run_time_limit = None
                else:
                    remaining_runs = max(1, total_runs_target - completed_runs)
                    remaining_time = max(0.1, max_runtime_seconds - elapsed)
                    run_time_limit = max(0.1, remaining_time / remaining_runs)

                run_seed = (
                    base_seed + cfg_idx * 1_000_000 + file_idx * 10_000 + run_idx
                )
                scheduler = SolutionMethod2(
                    instance_data=instance,
                    seed=run_seed,
                    population_size=params.population_size,
                    generations=params.generations,
                    mutation_rate=params.mutation_rate,
                    crossover_rate=params.crossover_rate,
                    gene_bonus_scale=params.gene_bonus_scale,
                    tournament_size=params.tournament_size,
                    run_time_limit=run_time_limit,
                )
                solution = scheduler.generate_solution()
                completed_runs += 1
                all_scores[params.name][file_path.name].append(solution.total_score)

                if save_run_outputs:
                    output_root.mkdir(parents=True, exist_ok=True)
                    out_name = (
                        f"{file_path.stem}_score_{int(solution.total_score)}"
                        f"_run_{run_idx:02d}_cfg_{cfg_idx}.json"
                    )
                    write_solution_json(solution, output_root / out_name, verbose=False)

    total_elapsed = time.perf_counter() - total_start

    # Aggregate statistics
    def _mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _std(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        m = _mean(values)
        var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return var ** 0.5

    per_config_summary: Dict[str, Dict[str, object]] = {}
    for params in parameter_sets:
        instance_rows = []
        cfg_scores: List[int] = []
        for f in files:
            scores = all_scores[params.name][f.name]
            if not scores:
                continue
            cfg_scores.extend(scores)
            instance_rows.append(
                {
                    "file": f.name,
                    "n": len(scores),
                    "best": max(scores),
                    "worst": min(scores),
                    "mean": round(_mean([float(s) for s in scores]), 2),
                    "std": round(_std([float(s) for s in scores]), 2),
                }
            )
        per_config_summary[params.name] = {
            "parameters": {
                "population_size": params.population_size,
                "generations": params.generations,
                "mutation_rate": params.mutation_rate,
                "crossover_rate": params.crossover_rate,
                "gene_bonus_scale": params.gene_bonus_scale,
                "tournament_size": params.tournament_size,
            },
            "instances": instance_rows,
            "overall_best": max(cfg_scores) if cfg_scores else None,
            "overall_mean": round(_mean([float(s) for s in cfg_scores]), 2) if cfg_scores else None,
        }

    print(
        f"Parameter study finished. Runs: {completed_runs}/{total_runs_target}. "
        f"Total time: {total_elapsed:.2f}s"
    )
    if save_run_outputs and completed_runs:
        print(f"Per-run solutions saved under: {output_root.resolve()}")
    for name, summary in per_config_summary.items():
        print(f"\n=== {name} ===")
        print(f"Overall mean score (all runs): {summary['overall_mean']}")
        for row in summary["instances"]:
            print(
                f"  {row['file']}: best={row['best']} mean={row['mean']} std={row['std']} (n={row['n']})"
            )

    return {
        "configs": [p.name for p in parameter_sets],
        "instances": [f.name for f in files],
        "per_config": per_config_summary,
        "completed_runs": completed_runs,
        "total_elapsed_s": total_elapsed,
        "output_root": str(output_root) if save_run_outputs else None,
    }


def run_ga_batch_single_config(
    json_path: Path,
    runs: int,
    base_seed: int,
    output_root: Path,
    *,
    population_size: int,
    generations: int,
    mutation_rate: float,
    crossover_rate: float,
    gene_bonus_scale: float,
    tournament_size: int,
    run_time_limit: Optional[float],
) -> None:
    """
    Run the GA ``runs`` times with the same hyperparameters (interactive default path).
    Writes ``{stem}_run_XX_score_<n>.json`` under ``output_root``.
    """
    if runs < 1:
        print("runs duhet të jetë ≥ 1")
        return
    json_path = json_path.resolve()
    if not json_path.is_file():
        print(f"Skedar nuk u gjet: {json_path}")
        sys.exit(1)

    parser = Parser(str(json_path))
    instance = parser.parse()
    Utils.set_current_instance(instance)
    output_root.mkdir(parents=True, exist_ok=True)

    total_start = time.perf_counter()
    for run_idx in range(runs):
        run_seed = base_seed + run_idx * 10_000
        scheduler = SolutionMethod2(
            instance_data=instance,
            seed=run_seed,
            population_size=population_size,
            generations=generations,
            mutation_rate=mutation_rate,
            crossover_rate=crossover_rate,
            gene_bonus_scale=gene_bonus_scale,
            tournament_size=tournament_size,
            run_time_limit=run_time_limit,
        )
        solution = scheduler.generate_solution()
        out_name = (
            f"{json_path.stem}_run_{run_idx:02d}_score_{int(solution.total_score)}.json"
        )
        write_solution_json(solution, output_root / out_name, verbose=False)

    elapsed = time.perf_counter() - total_start
    print(
        f"U ruajtën {runs} skedarë JSON në {output_root.resolve()} "
        f"(koha: {elapsed:.2f}s)"
    )


def spawn_ga_batch_background(
    json_path: Path,
    *,
    seed: int,
    runs: int,
    output_root: Path,
    population_size: int,
    generations: int,
    mutation_rate: float,
    crossover_rate: float,
    gene_bonus_scale: float,
    tournament_size: int,
    run_time_limit: Optional[float],
) -> None:
    """Detached ``--ga-batch-one`` for the same settings as :func:`run_ga_batch_single_config`."""
    script = Path(__file__).resolve()
    cmd = [
        sys.executable,
        str(script),
        "--ga-batch-one",
        str(json_path.resolve()),
        "--seed",
        str(seed),
        "--runs",
        str(runs),
        "--parameter-study-dir",
        str(output_root),
        "--population",
        str(population_size),
        "--generations",
        str(generations),
        "--mutation-rate",
        str(mutation_rate),
        "--crossover-rate",
        str(crossover_rate),
        "--gene-bonus-scale",
        str(gene_bonus_scale),
        "--tournament-size",
        str(tournament_size),
    ]
    if run_time_limit is not None:
        cmd.extend(["--run-time-limit", str(run_time_limit)])

    cwd = str(script.parent)
    popen_kw: Dict[str, object] = {
        "cwd": cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        popen_kw["start_new_session"] = True
    subprocess.Popen(cmd, **popen_kw)


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Run genetic scheduler method 2")
    arg_parser.add_argument("--input", "-i", dest="input_file", help="Path to input JSON (optional)")
    arg_parser.add_argument("--seed", type=int, default=42, help="Base random seed")
    arg_parser.add_argument("--population", type=int, default=24, help="GA population size")
    arg_parser.add_argument("--generations", type=int, default=25, help="GA generations")
    arg_parser.add_argument("--mutation-rate", type=float, default=0.08, help="GA mutation rate")
    arg_parser.add_argument("--crossover-rate", type=float, default=0.9, help="GA crossover rate")
    arg_parser.add_argument("--run-time-limit", type=float, default=None,
                            help="Per-run time limit in seconds (optional)")
    arg_parser.add_argument("--benchmark-10x10", action="store_true",
                            help="Run 10 instances x 10 executions with global runtime limit")
    arg_parser.add_argument(
        "--parameter-study",
        action="store_true",
        help="Run preset GA parameter sets (>=3), each instance runs_per_instance times",
    )
    arg_parser.add_argument("--gene-bonus-scale", type=float, default=50.0,
                            help="Weight for chromosome genes in selection score")
    arg_parser.add_argument("--tournament-size", type=int, default=3,
                            help="Tournament selection size")
    arg_parser.add_argument("--input-dir", default="data/input", help="Input directory for benchmark mode")
    arg_parser.add_argument("--instances", type=int, default=10, help="Number of instances for benchmark mode")
    arg_parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Runs per instance (benchmark / parameter study) or batch size when selecting "
        "instance interactively (default 10 JSON outputs)",
    )
    arg_parser.add_argument("--max-runtime", type=float, default=300.0,
                            help="Max total runtime in seconds for benchmark mode")
    arg_parser.add_argument(
        "--parameter-study-dir",
        type=str,
        default=str(DEFAULT_PARAMETER_STUDY_OUTPUT_DIR),
        help="Root folder for per-run JSON outputs when using --parameter-study",
    )
    arg_parser.add_argument(
        "--no-save-parameter-runs",
        action="store_true",
        help="Do not write run_XX_score_*.json files during --parameter-study",
    )
    arg_parser.add_argument(
        "--parameter-study-one",
        metavar="FILE",
        default=None,
        help="Run all preset parameter sets on a single instance (no global time cap); "
        "used internally for detached batch generation",
    )
    arg_parser.add_argument(
        "--ga-batch-one",
        metavar="FILE",
        default=None,
        help="Run GA --runs times on one JSON with current GA flags; save batch to "
        "--parameter-study-dir (non-interactive; used by interactive mode)",
    )
    args = arg_parser.parse_args()

    if args.ga_batch_one:
        run_ga_batch_single_config(
            Path(args.ga_batch_one),
            args.runs,
            args.seed,
            Path(args.parameter_study_dir),
            population_size=args.population,
            generations=args.generations,
            mutation_rate=args.mutation_rate,
            crossover_rate=args.crossover_rate,
            gene_bonus_scale=args.gene_bonus_scale,
            tournament_size=args.tournament_size,
            run_time_limit=args.run_time_limit,
        )
        return

    if args.parameter_study_one:
        one_path = Path(args.parameter_study_one)
        if not one_path.is_file():
            print(f"Skedar nuk u gjet: {one_path}")
            sys.exit(1)
        run_parameter_study(
            input_dir=str(one_path.parent),
            max_instances=1,
            runs_per_instance=args.runs,
            max_runtime_seconds=None,
            base_seed=args.seed,
            output_root=Path(args.parameter_study_dir),
            save_run_outputs=not args.no_save_parameter_runs,
            instance_paths=[one_path],
        )
        return

    if args.parameter_study:
        run_parameter_study(
            input_dir=args.input_dir,
            max_instances=args.instances,
            runs_per_instance=args.runs,
            max_runtime_seconds=args.max_runtime,
            base_seed=args.seed,
            output_root=Path(args.parameter_study_dir),
            save_run_outputs=not args.no_save_parameter_runs,
        )
        return

    if args.benchmark_10x10:
        run_benchmark_10x10(
            input_dir=args.input_dir,
            max_instances=args.instances,
            runs_per_instance=args.runs,
            max_runtime_seconds=args.max_runtime,
            base_seed=args.seed,
            population_size=args.population,
            generations=args.generations,
            mutation_rate=args.mutation_rate,
            crossover_rate=args.crossover_rate,
            gene_bonus_scale=args.gene_bonus_scale,
            tournament_size=args.tournament_size,
        )
        return

    if args.input_file:
        file_path = args.input_file
    else:
        file_path = select_file()
        out_dir = Path(args.parameter_study_dir)
        print()
        print(
            f"Po startohen {args.runs} ekzekutime GA në sfond → {out_dir.resolve()}\n"
            "(emrat: <instanca>_run_XX_score_<pikë>.json)"
        )
        spawn_ga_batch_background(
            Path(file_path),
            seed=args.seed,
            runs=args.runs,
            output_root=out_dir,
            population_size=args.population,
            generations=args.generations,
            mutation_rate=args.mutation_rate,
            crossover_rate=args.crossover_rate,
            gene_bonus_scale=args.gene_bonus_scale,
            tournament_size=args.tournament_size,
            run_time_limit=args.run_time_limit,
        )
        print("Procesi në sfond punon; mund ta mbyllësh këtë terminal.")
        return

    parser = Parser(file_path)
    instance = parser.parse()
    Utils.set_current_instance(instance)

    scheduler = SolutionMethod2(
        instance_data=instance,
        seed=args.seed,
        population_size=args.population,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        gene_bonus_scale=args.gene_bonus_scale,
        tournament_size=args.tournament_size,
        run_time_limit=args.run_time_limit,
    )
    solution = scheduler.generate_solution()

    serializer = SolutionSerializer(input_file_path=file_path, algorithm_name="genetic_method2")
    serializer.serialize(solution)

    print(f"Generated genetic Method 2 solution. Total score: {solution.total_score}")


if __name__ == "__main__":
    main()
