import argparse
import bisect
import json
import time
import random
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.channel import Channel
from models.instance_data import InstanceData
from models.program import Program
from models.schedule import Schedule
from models.solution import Solution
from parser.file_selector import select_file
from parser.parser import Parser
from serializer.serializer import SolutionSerializer
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
        seeded_solutions: Optional[List[List[dict]]] = None,
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
        self._program_lookup_exact = self._build_program_lookup_exact()
        self._seeded_population = self._build_seeded_population(seeded_solutions)

    def generate_solution(self) -> Solution:
        if self._chromosome_length == 0:
            return Solution(scheduled_programs=[], total_score=0)

        start_time = time.perf_counter()
        population = [chrom[:] for chrom in self._seeded_population]
        while len(population) < self.population_size:
            population.append(self._random_chromosome())
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

    def _build_program_lookup_exact(self) -> Dict[Tuple[int, str, int, int], int]:
        lookup: Dict[Tuple[int, str, int, int], int] = {}
        for idx, (channel, program) in enumerate(self._all_programs):
            key = (
                int(channel.channel_id),
                str(program.program_id),
                int(program.start),
                int(program.end),
            )
            lookup[key] = idx
        return lookup

    def _build_seeded_population(self, seeded_solutions: Optional[List[List[dict]]]) -> List[List[float]]:
        if not seeded_solutions:
            return []

        seeded_population: List[List[float]] = []
        for scheduled_programs in seeded_solutions:
            chromosome = self._seed_chromosome_from_scheduled_programs(scheduled_programs)
            if chromosome is not None:
                seeded_population.append(chromosome)
            if len(seeded_population) >= self.population_size:
                break

        return seeded_population

    def _seed_chromosome_from_scheduled_programs(
        self,
        scheduled_programs: Optional[List[dict]],
    ) -> Optional[List[float]]:
        if not scheduled_programs:
            return None

        chromosome = [0.0 for _ in range(self._chromosome_length)]
        matched = 0

        for item in scheduled_programs:
            try:
                key = (
                    int(item["channel_id"]),
                    str(item["program_id"]),
                    int(item["start"]),
                    int(item["end"]),
                )
            except (KeyError, TypeError, ValueError):
                continue

            gene_index = self._program_lookup_exact.get(key)
            if gene_index is None:
                continue

            if chromosome[gene_index] < 1.0:
                chromosome[gene_index] = 1.0
                matched += 1

        if matched == 0:
            return None

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
    run_time_limit: Optional[float] = None,
    seeded_solutions: Optional[List[List[dict]]] = None,
) -> Solution:
    """Convenience entry point requested by assignment."""
    scheduler = SolutionMethod2(
        instance_data=instance_data,
        seed=seed,
        population_size=population_size,
        generations=generations,
        mutation_rate=mutation_rate,
        crossover_rate=crossover_rate,
        run_time_limit=run_time_limit,
        seeded_solutions=seeded_solutions,
    )
    return scheduler.generate_solution()


def _extract_score_from_output_filename(file_path: Path) -> int:
    match = re.search(r"_(\d+)\.json$", file_path.name)
    if not match:
        return -1
    try:
        return int(match.group(1))
    except ValueError:
        return -1


def load_seeded_solutions_from_output(
    input_file: str,
    source_dir: str,
    limit: int,
) -> List[List[dict]]:
    base_name = Path(input_file).stem.replace("_input", "")
    source_path = Path(source_dir)
    if not source_path.exists():
        return []

    candidate_files = sorted(
        source_path.glob(f"{base_name}_output_*.json"),
        key=lambda p: _extract_score_from_output_filename(p),
        reverse=True,
    )

    seeded_solutions: List[List[dict]] = []
    for output_file in candidate_files:
        if len(seeded_solutions) >= limit:
            break

        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            scheduled_programs = data.get("scheduled_programs")
            if isinstance(scheduled_programs, list) and scheduled_programs:
                seeded_solutions.append(scheduled_programs)
        except Exception:
            continue

    return seeded_solutions


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
    output_dir: str,
    seed_population_from_output: bool,
    population_source_dir: str,
) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

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

        seeded_solutions = []
        if seed_population_from_output:
            seeded_solutions = load_seeded_solutions_from_output(
                input_file=str(file_path),
                source_dir=population_source_dir,
                limit=population_size,
            )
            if seeded_solutions:
                print(
                    f"[{file_idx + 1}/{len(files)}] Loaded {len(seeded_solutions)} seeded solutions "
                    f"from {population_source_dir} for {file_path.name}"
                )

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
                run_time_limit=run_time_limit,
                seeded_solutions=seeded_solutions,
            )
            solution = scheduler.generate_solution()
            completed_runs += 1

            if solution.total_score > best_score:
                best_score = solution.total_score
                best_solution = solution

        if best_solution is not None:
            serializer = SolutionSerializer(input_file_path=str(file_path), algorithm_name="genetic_method2")
            serializer.output_dir = Path(output_dir)
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


def run_single_instance_benchmark(
    input_file: str,
    runs: int,
    max_runtime_seconds: float,
    base_seed: int,
    population_size: int,
    generations: int,
    mutation_rate: float,
    crossover_rate: float,
    output_dir: str,
    seed_population_from_output: bool,
    population_source_dir: str,
) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    parser = Parser(input_file)
    instance = parser.parse()
    Utils.set_current_instance(instance)

    seeded_solutions = []
    if seed_population_from_output:
        seeded_solutions = load_seeded_solutions_from_output(
            input_file=input_file,
            source_dir=population_source_dir,
            limit=population_size,
        )
        if seeded_solutions:
            print(
                f"Loaded {len(seeded_solutions)} seeded solutions from "
                f"{population_source_dir} for {Path(input_file).name}"
            )

    best_solution: Optional[Solution] = None
    best_score = float("-inf")
    completed_runs = 0
    total_start = time.perf_counter()

    print(
        f"Starting single-instance benchmark: runs={runs}, max_runtime={max_runtime_seconds:.1f}s, "
        f"input={Path(input_file).name}"
    )

    for run_idx in range(runs):
        elapsed = time.perf_counter() - total_start
        if elapsed >= max_runtime_seconds:
            print(
                f"Time limit reached after {elapsed:.2f}s. "
                f"Completed runs: {completed_runs}/{runs}"
            )
            break

        remaining_runs = max(1, runs - completed_runs)
        remaining_time = max(0.1, max_runtime_seconds - elapsed)
        run_time_limit = max(0.1, remaining_time / remaining_runs)

        run_seed = base_seed + run_idx
        scheduler = SolutionMethod2(
            instance_data=instance,
            seed=run_seed,
            population_size=population_size,
            generations=generations,
            mutation_rate=mutation_rate,
            crossover_rate=crossover_rate,
            run_time_limit=run_time_limit,
            seeded_solutions=seeded_solutions,
        )
        solution = scheduler.generate_solution()
        completed_runs += 1

        print(f"Run {run_idx + 1}/{runs} score: {solution.total_score}")

        if solution.total_score > best_score:
            best_score = solution.total_score
            best_solution = solution

    if best_solution is not None:
        serializer = SolutionSerializer(input_file_path=input_file, algorithm_name="genetic_method2_single")
        serializer.output_dir = Path(output_dir)
        serializer.serialize(best_solution)
        print(f"Best score from single-instance benchmark: {best_solution.total_score}")

    total_elapsed = time.perf_counter() - total_start
    print(
        f"Single-instance benchmark completed. Executed runs: {completed_runs}/{runs}. "
        f"Total time: {total_elapsed:.2f}s"
    )


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
    arg_parser.add_argument("--input-dir", default="data/input", help="Input directory for benchmark mode")
    arg_parser.add_argument("--instances", type=int, default=10, help="Number of instances for benchmark mode")
    arg_parser.add_argument("--runs", type=int, default=10, help="Runs per instance for benchmark mode")
    arg_parser.add_argument("--max-runtime", type=float, default=300.0,
                            help="Max total runtime in seconds for benchmark mode")
    arg_parser.add_argument("--single-10x", action="store_true",
                            help="Run one selected instance multiple times (default 10) within max-runtime")
    arg_parser.add_argument("--output-dir", default="data/output_algo2",
                            help="Directory where output JSON files are saved")
    arg_parser.add_argument(
        "--seed-population-from-output",
        action="store_true",
        help="Seed GA initial population using existing schedules from output JSON files",
    )
    arg_parser.add_argument(
        "--population-source-dir",
        default="data/output",
        help="Directory containing existing output JSON files used for population seeding",
    )
    args = arg_parser.parse_args()

    # Default behavior: if no benchmark mode is requested explicitly,
    # run single-instance 10x benchmark with seeded population.
    if not args.benchmark_10x10 and not args.single_10x:
        args.single_10x = True
        args.seed_population_from_output = True

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

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
            output_dir=args.output_dir,
            seed_population_from_output=args.seed_population_from_output,
            population_source_dir=args.population_source_dir,
        )
        return

    file_path = args.input_file if args.input_file else select_file()

    if args.single_10x:
        run_single_instance_benchmark(
            input_file=file_path,
            runs=args.runs,
            max_runtime_seconds=args.max_runtime,
            base_seed=args.seed,
            population_size=args.population,
            generations=args.generations,
            mutation_rate=args.mutation_rate,
            crossover_rate=args.crossover_rate,
            output_dir=args.output_dir,
            seed_population_from_output=args.seed_population_from_output,
            population_source_dir=args.population_source_dir,
        )
        return

    parser = Parser(file_path)
    instance = parser.parse()
    Utils.set_current_instance(instance)

    solution = solution_method2(
        instance,
        seed=args.seed,
        population_size=args.population,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        run_time_limit=args.run_time_limit,
        seeded_solutions=(
            load_seeded_solutions_from_output(
                input_file=file_path,
                source_dir=args.population_source_dir,
                limit=args.population,
            )
            if args.seed_population_from_output
            else None
        ),
    )

    serializer = SolutionSerializer(input_file_path=file_path, algorithm_name="genetic_method2")
    serializer.output_dir = Path(args.output_dir)
    serializer.serialize(solution)

    print(f"Generated genetic Method 2 solution. Total score: {solution.total_score}")
    print(f"Saved to output directory: {os.path.abspath(args.output_dir)}")


if __name__ == "__main__":
    main()
