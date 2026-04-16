from models.instance_data import InstanceData
from models.schedule import Schedule
from models.solution import Solution
from utils.algorithm_utils import AlgorithmUtils
from utils.scheduler_utils import SchedulerUtils


class GreedyScheduler:

    def __init__(self, instance_data: InstanceData):
        self.instance_data = instance_data

    def generate_solution(self) -> Solution:
        time = self.instance_data.opening_time

        total_score = 0
        solution = []

        while time < self.instance_data.closing_time:
            valid_channel_indexes = SchedulerUtils.get_valid_schedules(scheduled_programs=solution,
                                                                       instance_data=self.instance_data,
                                                                       schedule_time=time)
            if not valid_channel_indexes:
                time += 1
                continue

            best_channel, channel_program, fitness = AlgorithmUtils.get_best_fit(scheduled_programs=solution,
                                                                                 instance_data=self.instance_data,
                                                                                 schedule_time=time,
                                                                                 valid_channel_indexes=valid_channel_indexes)

            if not best_channel or not channel_program or fitness <= 0:
                time += 1
                continue

            # Check if we're trying to schedule the exact same program again
            if solution and solution[-1].unique_program_id == channel_program.unique_id:
                time += 1
                continue

            # Check if this program would overlap with the previous program
            if solution and channel_program.start < solution[-1].end:
                # Can't schedule - would create overlap
                time += 1
                continue

            # Check if this program meets minimum duration requirement
            if channel_program.end - channel_program.start < self.instance_data.min_duration:
                # Program itself is too short
                time += 1
                continue

            # Use the program's actual start and end times
            schedule = Schedule(program_id=channel_program.program_id, channel_id=best_channel.channel_id,
                                start=channel_program.start, end=channel_program.end, fitness=fitness,
                                unique_program_id=channel_program.unique_id)

            solution.append(schedule)
            # Move time to the end of the scheduled program
            time = channel_program.end
            total_score += fitness

        return Solution(scheduled_programs=solution, total_score=total_score)
