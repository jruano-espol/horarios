from enum import IntEnum
from dataclasses import dataclass
from collections import defaultdict
from itertools import product
import pandas as pd
import dash
from dash import Input, Output, State, dash_table, html, dcc

FILENAME = "Horarios Semestre 6.md"


class Day(IntEnum):
    Monday    = 1<<0
    Tuesday   = 1<<1
    Wednesday = 1<<2
    Thursday  = 1<<3
    Friday    = 1<<4
    Count     = 5


def str_from_day(day: Day) -> str:
    match day:
        case Day.Monday:    return "lun"
        case Day.Tuesday:   return "mar"
        case Day.Wednesday: return "mie"
        case Day.Thursday:  return "jue"
        case Day.Friday:    return "vie"
        case _: assert False


def str_from_days(days: int) -> str:
    builder = []
    for i in range(Day.Count):
        if days & (1 << i):
            builder.append(str_from_day(1 << i))
    return '-'.join(builder)


@dataclass
class Hour:
    hours:   int
    minutes: int


def str_from_hour(hour: Hour) -> str:
    return f"{hour.hours:02d}:{hour.minutes:02d}"


@dataclass
class Hour_Range:
    start: Hour
    end:   Hour


def str_from_hours(hours: Hour_Range) -> str:
    return f'{str_from_hour(hours.start)}-{str_from_hour(hours.end)}'


def do_hours_overlap(range1: Hour_Range, range2: Hour_Range) -> bool:
    return not ((range1.end.hours < range2.start.hours) or
                (range1.end.hours == range2.start.hours and range1.end.minutes <= range2.start.minutes) or
                (range1.start.hours > range2.end.hours) or
                (range1.start.hours == range2.end.hours and range1.start.minutes >= range2.end.minutes))


@dataclass
class Exam:
    id: int
    hours: Hour_Range
    in_person: bool


def str_from_exam(exam: Exam):
    in_person = "presencial" if exam.in_person else "virtual"
    return f'(exámen: {exam.id} {str_from_hours(exam.hours)} {in_person})'


def do_exams_overlap(exam1: Exam, exam2: Exam) -> bool:
    if exam1.id != exam2.id:
        return False
    return do_hours_overlap(exam1.hours, exam2.hours)


@dataclass
class Schedule:
    group: int
    days: int
    hours: Hour_Range
    in_person: bool
    available: int
    exam: Exam


@dataclass
class Class:
    name: str
    options: list[Schedule]
    exam: Exam


def parse_days(line: str) -> (int, int):
    has = [
        line.find("lun") >= 0,
        line.find("mar") >= 0,
        line.find("mie") >= 0,
        line.find("jue") >= 0,
        line.find("vie") >= 0,
    ]
    assert Day.Count == len(has)

    days = 0
    for i in range(Day.Count):
        if has[i]:
            days |= (1 << i)

    return days, line.find(' ')


def parse_in_person(line: str) -> (bool, int):
    P, V = 'presencial', 'virtual'
    p, v = line.find(P), line.find(V)
    if p >= 0:
        return True, p + len(P)
    return False, v + len(V)


def parse_hours(line: str) -> (Hour_Range, int):
    start, end = Hour(0, 0), Hour(0, 0)
    count = 0

    next = line.find(':'); assert next >= 0
    start.hours = int(line[:next])
    line = line[next + 1:] ; count += next + 1

    next = line.find('-'); assert next >= 0
    start.minutes = int(line[:next])
    line = line[next + 1:] ; count += next + 1

    next = line.find(':'); assert next >= 0
    end.hours = int(line[:next])
    line = line[next + 1:] ; count += next + 1

    next = line.find(' '); assert next >= 0
    end.minutes = int(line[:next])
    line = line[next + 1:] ; count += next + 1

    return Hour_Range(start, end), count - 1


def parse_exam(line) -> Exam:
    next = line.find(' '); assert next >= 0
    line = line[next + 1:]

    next = line.find(' '); assert next >= 0
    id = int(line[:next])
    line = line[next + 1:]

    hours, _ = parse_hours(line)
    in_person = line.find("presencial") >= 0

    return Exam(id, hours, in_person)


def parse_schedule(line: str, maybe_exam: Exam):
    line = line[len("- Paralelo "):]

    next = line.find(' '); assert next >= 0
    group = int(line[:next - 1])
    line = line[next + 1:]

    days, next = parse_days(line) ; assert next >= 0
    line = line[next + 1:]

    hours, next = parse_hours(line) ; assert next >= 0
    line = line[next + 1:]

    in_person, next = parse_in_person(line) ; assert next >= 0
    line = line[next + 1:]

    next = line.find(' '); assert next >= 0
    available = int(line[:next])
    line = line[next + 1:]

    next = line.find('(');
    if next >= 0:
        line = line[next + 1:]
        exam = parse_exam(line)
    else:
        exam = maybe_exam

    return Schedule(group, days, hours, in_person, available, exam)


def parse_title(line: str) -> Class:
    x = line.find('(')
    if x != -1:
        return Class(name=line[:x].strip(), options=[], exam=parse_exam(line[x:]))
    return Class(name=line.strip(': '), options=[], exam=None)


def parse_semester_line(lines: list[str]) -> list[Class]:
    classes = []

    for current_line in range(0, len(lines)):
        line = lines[current_line].strip()
        if line[0] == '-':
            last = classes[len(classes) - 1]
            last.options.append(parse_schedule(line, last.exam))
        else:
            classes.append(parse_title(line))

    return classes


def show_semester_line(classes: list[Class], show_options=True):
    if show_options:
        for c in classes:
            print(f'{c.name}:')
            for schedule in c.options:
                in_person = "presencial" if schedule.in_person else "virtual"
                print(f' - Paralelo {schedule.group:02d}: {str_from_days(schedule.days)} {str_from_hours(schedule.hours)} {in_person} {schedule.available} cupos {str_from_exam(schedule.exam)}')
            print('')
    else:
        for c in classes:
            print(f'- {c.name}')


def generate_valid_combinations(classes: list[Class]) -> list[list[tuple[str, Schedule]]]:
    all_combinations = list(product(*([(cls.name, schedule) for schedule in cls.options] for cls in classes)))
    valid_combinations = []

    for combination in all_combinations:
        is_valid = True
        for i in range(len(combination)):
            for j in range(i + 1, len(combination)):
                if do_hours_overlap(combination[i][1].hours, combination[j][1].hours):
                    is_valid = False
                    break
                if do_exams_overlap(combination[i][1].exam, combination[j][1].exam):
                    is_valid = False
                    break

            if not is_valid:
                break

        if is_valid:
            valid_combinations.append(list(combination))

    return valid_combinations


def get_day_layout_div(valid_combination: list[tuple]) -> str:
    root = html.Ul([])

    # Group schedules by the days they are active using the bit flags
    schedules_by_day = defaultdict(list)

    for class_name, schedule in valid_combination:
        for i in range(Day.Count):
            if schedule.days & (1 << i):
                schedules_by_day[i].append((class_name, schedule))

    # Iterate over each day and print its schedule
    for day_num in range(Day.Count):
        if day_num in schedules_by_day:
            schedules = schedules_by_day[day_num]
            day_str = str_from_day(1 << day_num)

            li = html.Li([])
            li.children.append(f"{day_str.capitalize()}:")

            # Sort schedules by their start time to display them in order
            schedules.sort(key=lambda x: (x[1].hours.start.hours, x[1].hours.start.minutes))

            ul = html.Ul([])
            for class_name, schedule in schedules:
                time_range = str_from_hours(schedule.hours)
                group = schedule.group
                ul.children.append(html.Li(f"    {time_range} Paralelo {group:02d}: {class_name}"))
            li.children.append(ul)
            root.children.append(li)

    return root


def dataframe_from_valid_combination(valid_combination: list[tuple[str, Schedule]]) -> pd.DataFrame :
    # Create an empty DataFrame to represent the schedule
    days_of_week = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
    time_slots = [f"{h:02}:{m:02}" for h in range(7, 24) for m in [0, 30]]  # 07:00 to 23:00, half-hour intervals
    data = []

    # Initialize a dictionary for each day
    schedule_dict = {day: [""] * len(time_slots) for day in days_of_week}

    for class_name, schedule in valid_combination:
        # Calculate start and end time slots
        start_time = schedule.hours.start.hours * 60 + schedule.hours.start.minutes  # In minutes
        end_time = schedule.hours.end.hours * 60 + schedule.hours.end.minutes  # In minutes

        # Find the corresponding rows for start and end times
        start_row = (start_time - 7 * 60) // 30
        end_row = (end_time - 7 * 60) // 30

        # Fill the schedule for the corresponding days
        for i in range(Day.Count):
            if schedule.days & (1 << i):  # If this day is active
                day = days_of_week[i]
                for row in range(start_row, end_row):
                    if schedule_dict[day][row] == "":
                        schedule_dict[day][row] = f"{class_name} Paralelo {schedule.group}"

    # Convert the schedule dictionary to a list of rows
    for time, row in zip(time_slots, range(len(time_slots))):
        data_row = [time] + [schedule_dict[day][row] for day in days_of_week]
        data.append(data_row)

    # Create the DataFrame for easy table plotting
    df = pd.DataFrame(data, columns=["Time"] + days_of_week)
    return df


def main():
    with open(FILENAME, 'r', encoding='utf-8') as file:
        lines = file.read().split('\n')
        lines = [x.strip() for x in lines if len(x.strip()) > 0]

        prev_line_idx = lines.index('## Obligatorio')
        this_line_idx = lines.index('## Opciones')

        prev_line_lines = lines[prev_line_idx+1:this_line_idx]
        this_line_lines = lines[this_line_idx+1:]

        prev_line = parse_semester_line(prev_line_lines)
        this_line = parse_semester_line(this_line_lines)

        # show_options = False
        # print('-'*90)
        # show_semester_line(prev_line, show_options)
        # print('-'*90)
        # show_semester_line(this_line, show_options)
        # print('-'*90)

        classes = []
        classes.extend(prev_line)
        classes.append(this_line[0])
        classes.append(this_line[3])

        valid_combinations = generate_valid_combinations(classes)
        dataframes = [dataframe_from_valid_combination(choice) for choice in valid_combinations]
        day_layout_divs = [get_day_layout_div(choice) for choice in valid_combinations]

        idx = 0
        app = dash.Dash(__name__)

        if len(valid_combinations) > 0:
            df = dataframes[idx]
            day_layout_div = day_layout_divs[idx]

            app.layout = html.Div([

                dcc.Store(id='current-index', data=idx),

                html.P(id='current-schedule', children=f"Schedule #{idx+1} of {len(valid_combinations)}"),

                html.Div([
                    html.Button('<<', id='left-arrow-max',  n_clicks=0, style={'margin-right': '10px'}),
                    html.Button('←',  id='left-arrow',      n_clicks=0, style={'margin-right': '10px'}),
                    html.Button('→',  id='right-arrow',     n_clicks=0, style={'margin-right': '10px'}),
                    html.Button('>>', id='right-arrow-max', n_clicks=0),
                ]),

                html.Div(id='schedule-layout', children=[day_layout_div]),

                dash_table.DataTable(
                    id='schedule-table',
                    columns=[{"name": col, "id": col} for col in df.columns],
                    data=df.to_dict('records'),
                    style_table={
                        'height': '100vh',
                        'width': '100%',
                    },
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': '10px',
                        'height': 'auto',
                        'width': 'auto',
                    },
                    style_header={
                        'fontWeight': 'bold',
                        'backgroundColor': 'lightgray'
                    }
                ),
            ])

            @app.callback(
                [Output('current-index',    'data'),
                 Output('current-schedule', 'children'),
                 Output('schedule-table',   'data'),
                 Output('schedule-layout',  'children')],
                [Input('left-arrow-max',  'n_clicks'),
                 Input('left-arrow',      'n_clicks'),
                 Input('right-arrow',     'n_clicks'),
                 Input('right-arrow-max', 'n_clicks')],
                [State('current-index', 'data')]
            )
            def update_schedule(clicks_l_max, clicks_l, clicks_r, clicks_r_max, idx):
                if len(valid_combinations) == 0:
                    return idx, None, None, None

                last_valid = len(valid_combinations) - 1
                triggered_id = dash.callback_context.triggered[0]['prop_id'].split('.')[0]

                match triggered_id:
                    case "left-arrow-max":  idx = 0
                    case "right-arrow-max": idx = last_valid
                    case "left-arrow":
                        if idx > 0:
                            idx -= 1
                    case "right-arrow":
                        if idx < last_valid:
                            idx += 1

                df = dataframes[idx]
                day_layout_div = day_layout_divs[idx]
                current_schedule = f"Schedule #{idx+1} of {len(valid_combinations)}"

                return idx, current_schedule, df.to_dict('records'), day_layout_div
        else:
            app.layout = html.Div([
                html.P(f"There are no possible schedules."),
            ])

        app.run(debug=True)


if __name__ == "__main__":
    main()
