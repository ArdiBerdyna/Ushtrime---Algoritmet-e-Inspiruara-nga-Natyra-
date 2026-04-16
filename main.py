from parser.file_selector import select_file
from parser.parser import Parser
from scheduler.greedy_scheduler import GreedyScheduler
from scheduler.greedy_lookahead import GreedyLookahead
from scheduler.beam_search import BeamSearchScheduler
from serializer.serializer import SolutionSerializer
from scheduler.beam_search_advanced import BeamSearchSchedulerAdvanced
from scheduler.beyond_dynamic_beam_search import BeyondDynamicBeamSearchSchedulerAdvanced
from utils.utils import Utils
from scheduler.upper_bound_greedy import UpperBoundGreedy
import argparse


def main():
    parser_arg = argparse.ArgumentParser(description="Run TV scheduling algorithms")
    parser_arg.add_argument("--input", "-i", dest="input_file", help="Path to input JSON (optional)")
    parser_arg.add_argument("--scheduler", "-s", dest="scheduler",
                            choices=["1", "2", "3", "4"],
                            help="Scheduler to use: 1=Greedy,2=GreedyLookahead,3=Beam,4=BeamAdvanced")
    parser_arg.add_argument("--beam-width", type=int, default=3, help="Base beam width for beam schedulers")
    parser_arg.add_argument("--jump-cap", type=int, default=30, help="Jump cap (minutes) for beam search")
    parser_arg.add_argument("--backtrack-window", type=int, default=10, help="Backtrack window size for beam search")
    parser_arg.add_argument("--restarts", type=int, default=3, help="Restarts for advanced beam search")
    parser_arg.add_argument("--iterative-deepening", action="store_true",
                            help="Enable iterative deepening for advanced scheduler")
    parser_arg.add_argument("--max-beam-multiplier", type=int, default=3,
                            help="Max multiplier for iterative deepening")
    parser_arg.add_argument("--time-limit", type=float, default=None, help="Time limit (seconds) for advanced scheduler phases")

    args = parser_arg.parse_args()
    file_path = args.input_file if args.input_file else select_file()
    parser = Parser(file_path)
    instance = parser.parse()
    Utils.set_current_instance(instance)

    print("\nOpening time:", instance.opening_time)
    print("Closing time:", instance.closing_time)
    print("Channels:")
    for ch in instance.channels:
        print(f"  Channel {ch.channel_name}:")
        for p in ch.programs:
            print(f"    {p.program_id} | {p.start}-{p.end} | {p.genre} | Score: {p.score}")

    print('\nChoose scheduler:')
    print('1: GreedyScheduler (original)')
    print('2: GreedyLookahead (lookahead greedy)')
    print('3: Beam_Search (bounded lookahead)')
    print('4: Beam_Search_Advanced (advanced lookahead)')
    print('5: Upper Bound')
    print('6: Beyond Dynamic Beam Search + Iterative Deepening + Advanced Backtracking')

    choice = input('Select scheduler [1/2/3/4/5/6] (default 1): ').strip() or '1'

    if choice == '2':
        scheduler = GreedyLookahead(instance)
    elif choice == '3':
        scheduler = BeamSearchScheduler(instance)
    elif choice == '4':
        scheduler = BeamSearchSchedulerAdvanced(instance)
    elif choice == '5':
        scheduler = UpperBoundGreedy(
            instance_data=instance,
            fixed_duration=30,
            include_all_preferences=True
        )
    elif choice == '6':
        print("\nYou selected: Beyond Dynamic Beam Search + Iterative Deepening + Advanced Backtracking")

        beam_width = int(input("Enter beam width (default 3): ") or 3)
        restarts = int(input("Enter number of restarts (default 3): ") or 3)
        iterative_input = input("Enable iterative deepening? (y/n, default y): ").strip().lower() or 'y'
        iterative_deepening = iterative_input == 'y'
        max_beam_multiplier = int(input("Enter max beam multiplier (default 3): ") or 3)
        time_limit_input = input("Enter time limit in seconds (or leave empty for no limit): ").strip()
        time_limit = float(time_limit_input) if time_limit_input else None

        scheduler = BeyondDynamicBeamSearchSchedulerAdvanced(
            instance_data=instance,
            beam_width=beam_width,
            jump_cap=args.jump_cap,
            backtrack_window=args.backtrack_window,
            iterative_deepening=iterative_deepening,
            max_beam_multiplier=max_beam_multiplier
        )

        print(f"\nRunning advanced scheduler with parameters:"
              f"\n - beam_width={beam_width}"
              f"\n - restarts={restarts}"
              f"\n - iterative_deepening={iterative_deepening}"
              f"\n - max_beam_multiplier={max_beam_multiplier}"
              f"\n - time_limit={time_limit}")

        if time_limit:
            solution = scheduler.generate_solution_with_time(restarts=restarts, time_limit=time_limit)
        else:
            solution = scheduler.generate_solution(restarts=restarts)
    else:
        scheduler = GreedyScheduler(instance)

    # For advanced scheduler allow restarts to be set via CLI
    if choice != '6':
        if isinstance(scheduler, BeamSearchSchedulerAdvanced):
            # If time_limit provided use the time-aware generator
            if args.time_limit:
                solution = scheduler.generate_solution_with_time(restarts=args.restarts, time_limit=args.time_limit)
            else:
                solution = scheduler.generate_solution(restarts=args.restarts)
        else:
            solution = scheduler.generate_solution()
    print(f"\n✓ Generated solution with total score: {solution.total_score}")

    algorithm_name = type(scheduler).__name__.lower()
    serializer = SolutionSerializer(input_file_path=file_path, algorithm_name=algorithm_name)
    serializer.serialize(solution)

    print(f"✓ Solution saved to output file")


if __name__ == "__main__":
    main()
