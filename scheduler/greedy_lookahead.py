from typing import Tuple
from models.instance_data import InstanceData
from models.schedule import Schedule
from models.solution import Solution
from utils.scheduler_utils import SchedulerUtils
from utils.utils import Utils
from utils.algorithm_utils import AlgorithmUtils
from models.schedule import Schedule as ScheduleModel

class GreedyLookahead:

    def __init__(self, instance_data: InstanceData):
        self.instance_data = instance_data

    def generate_solution(self) -> Solution:
        # Deterministic single pass
        solution, total_score = self._single_run()
        return Solution(scheduled_programs=solution, total_score=total_score)

    def _single_run(self) -> Tuple[list[Schedule], int]:
        time = self.instance_data.opening_time
        # Build a local cache: channel object id -> index to avoid repeated enumerate
        channel_to_index = {id(ch): idx for idx, ch in enumerate(self.instance_data.channels)}

        total_score = 0
        solution: list[Schedule] = []

        while time < self.instance_data.closing_time:
            valid_channel_indexes = SchedulerUtils.get_valid_schedules(scheduled_programs=solution,
                                                                       instance_data=self.instance_data,
                                                                       schedule_time=time)
            if not valid_channel_indexes:
                # minute-skipping: jump to next earliest program start among all channels >= time
                next_start = None
                for ch in self.instance_data.channels:
                    for p in ch.programs:
                        if p.start > time:
                            if next_start is None or p.start < next_start:
                                next_start = p.start
                time = next_start if next_start is not None else time + 1
                continue

            # Evaluate candidates using 1-step lookahead: choose program now and add best next choice at its end
            max_score = float('-inf')
            best_channel = None
            best_program = None

            for channel_index in valid_channel_indexes:
                channel = self.instance_data.channels[channel_index]
                # Lookup current program
                program = Utils.get_channel_program_by_time(channel, time)

                if not program:
                    continue

                # score now
                score_now = 0
                score_now += program.score
                score_now += AlgorithmUtils.get_time_preference_bonus(self.instance_data, program, time)
                score_now += AlgorithmUtils.get_switch_penalty(solution, self.instance_data, channel)
                score_now += AlgorithmUtils.get_delay_penalty(solution, self.instance_data, program, time)
                score_now += AlgorithmUtils.get_early_termination_penalty(solution, self.instance_data, program, time)

                # Build a temporary schedule to simulate the state after picking this program
                temp_schedule = ScheduleModel(program_id=program.program_id, channel_id=channel.channel_id,
                                              start=program.start, end=program.end, fitness=int(score_now),
                                              unique_program_id=program.unique_id)
                simulated_plan = solution + [temp_schedule]

                # Evaluate best next choice at program.end (next scheduling moment)
                future_best = 0
                future_time = program.end
                if future_time < self.instance_data.closing_time:
                    valid_next = SchedulerUtils.get_valid_schedules(scheduled_programs=simulated_plan,
                                                                    instance_data=self.instance_data,
                                                                    schedule_time=future_time)
                    if valid_next:
                        _, _, future_best = AlgorithmUtils.get_best_fit(scheduled_programs=simulated_plan,
                                                                       instance_data=self.instance_data,
                                                                       schedule_time=future_time,
                                                                       valid_channel_indexes=valid_next)

                # Total score for selection purposes (includes future lookahead)
                score = score_now + future_best

                if score > max_score:
                    max_score = score
                    best_channel = channel
                    best_program = program

            # Fitness for THIS step only (not including future lookahead)
            # We need to recalculate score_now for the selected program
            if best_program:
                fitness = 0
                fitness += best_program.score
                fitness += AlgorithmUtils.get_time_preference_bonus(self.instance_data, best_program, time)
                fitness += AlgorithmUtils.get_switch_penalty(solution, self.instance_data, best_channel)
                fitness += AlgorithmUtils.get_delay_penalty(solution, self.instance_data, best_program, time)
                fitness += AlgorithmUtils.get_early_termination_penalty(solution, self.instance_data, best_program, time)
            else:
                fitness = 0

            # Remove the incorrect condition preventing same channel consecutively
            # Also check that we found a valid program
            if not best_channel or not best_program or fitness <= 0:
                time += 1
                continue

            # Check if we're trying to schedule the exact same program again
            if solution and solution[-1].unique_program_id == best_program.unique_id:
                time += 1
                continue

            # Check if this program would overlap with the previous program
            if solution and best_program.start < solution[-1].end:
                # Can't schedule - would create overlap
                time += 1
                continue

            # Check if this program meets minimum duration requirement
            if best_program.end - best_program.start < self.instance_data.min_duration:
                # Program itself is too short
                time += 1
                continue

            # Use the program's actual start and end times
            schedule = Schedule(program_id=best_program.program_id, channel_id=best_channel.channel_id,
                                start=best_program.start, end=best_program.end, fitness=fitness,
                                unique_program_id=best_program.unique_id)

            solution.append(schedule)
            # Move time to the end of the scheduled program
            time = best_program.end
            total_score += fitness

        return solution, total_score