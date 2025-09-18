from enum import IntEnum
from dataclasses import dataclass
from collections import defaultdict
import colorsys
import itertools
import pandas as pd
import dash
from dash import Input, Output, State, dash_table, html, dcc


FILENAME = "Horarios Semestre 6.md"
DAYS_OF_WEEK = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


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


def hour_from_str(s: str) -> Hour:
    parts = s.split(':')
    assert len(parts) == 2
    return Hour(hours=int(parts[0].strip()), minutes=int(parts[1].strip()))


@dataclass
class Hour_Range:
    start: Hour
    end:   Hour


def str_from_hour_range(hours: Hour_Range) -> str:
    return f'{str_from_hour(hours.start)}-{str_from_hour(hours.end)}'


def hour_range_from_str(s: str) -> Hour_Range:
    parts = s.split('-')
    assert len(parts) == 2
    return Hour_Range(start=hour_from_str(parts[0].strip()), end=hour_from_str(parts[1].strip()))


def do_hours_overlap(range1: Hour_Range, range2: Hour_Range) -> bool:
    return not ((range1.end.hours < range2.start.hours) or
                (range1.end.hours == range2.start.hours and range1.end.minutes <= range2.start.minutes) or
                (range1.start.hours > range2.end.hours) or
                (range1.start.hours == range2.end.hours and range1.start.minutes >= range2.end.minutes))


def check_hours_overlap(ranges: list[Hour_Range]) -> bool:
    if len(ranges) <= 1:
        return False
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            if do_hours_overlap(ranges[i], ranges[j]):
                return True
    return False


@dataclass
class Exam:
    id: int
    hours: Hour_Range
    in_person: bool


def str_from_exam(exam: Exam):
    in_person = "presencial" if exam.in_person else "virtual"
    return f'(exámen: {exam.id} {str_from_hour_range(exam.hours)} {in_person})'


def do_exams_overlap(exam1: Exam, exam2: Exam) -> bool:
    if exam1.id != exam2.id:
        return False
    return do_hours_overlap(exam1.hours, exam2.hours)


def check_exams_overlap(exams: list[Exam]) -> bool:
    if len(exams) <= 1:
        return False
    for i in range(len(exams)):
        for j in range(i + 1, len(exams)):
            if do_exams_overlap(exams[i], exams[j]):
                return True
    return False


@dataclass
class Schedule:
    group: int
    days: int
    hours: Hour_Range
    in_person: bool
    available: int
    exam: Exam
    associated_class: 'Class'


def is_schedule_valid(schedule: Schedule, accepted: Hour_Range) -> bool:
    schedule_start = schedule.hours.start.hours * 60 + schedule.hours.start.minutes
    schedule_end = schedule.hours.end.hours * 60 + schedule.hours.end.minutes
    accepted_start = accepted.start.hours * 60 + accepted.start.minutes
    accepted_end = accepted.end.hours * 60 + accepted.end.minutes

    is_accepted = (schedule_start >= accepted_start) and (schedule_end <= accepted_end)
    return is_accepted


def is_schedule_arrangement_valid(schedules: list[Schedule], accepted: Hour_Range) -> bool:
    if len(schedules) <= 1:
        return True
    if check_exams_overlap([schedule.exam for schedule in schedules]):
        return False
    day_hours = {i: [] for i in range(Day.Count)}
    for schedule in schedules:
        if not is_schedule_valid(schedule, accepted):
            return False
        for i in range(Day.Count):
            if schedule.days & (1 << i):
                day_hours[i].append(schedule.hours)
    for _, hours in day_hours.items():
        if check_hours_overlap(hours):
            return False
    return True


@dataclass
class Class:
    name: str
    options: list[Schedule]
    exam: Exam


def parse_days(line: str) -> tuple[int, int]:
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


def parse_in_person(line: str) -> tuple[bool, int]:
    P, V = 'presencial', 'virtual'
    p, v = line.find(P), line.find(V)
    if p >= 0:
        return True, p + len(P)
    return False, v + len(V)


def parse_hours(line: str) -> tuple[Hour_Range, int]:
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


def parse_schedule(line: str, associated_class: Class):
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

    next = line.find('(')
    if next >= 0:
        line = line[next + 1:]
        exam = parse_exam(line)
    else:
        exam = associated_class.exam

    return Schedule(group, days, hours, in_person, available, exam, associated_class)


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
            last.options.append(parse_schedule(line, last))
        else:
            classes.append(parse_title(line))

    return classes


def pretty_print_schedule(schedule: Schedule, option_index: int):
    in_person = "presencial" if schedule.in_person else "virtual"
    class_line = [
        f'{option_index:02d}.',
        f'Paralelo {schedule.group:02d}:',
        f'{str_from_days(schedule.days)}',
        f'{str_from_hour_range(schedule.hours)}',
        f'{in_person}',
        f'{schedule.available} cupos',
        f'{str_from_exam(schedule.exam)}',
    ]
    class_line = " ".join(class_line)
    print(class_line)


def show_semester_line(classes: list[Class], show_options=True):
    if show_options:
        for c in classes:
            print(f'{c.name}:')
            for index, schedule in enumerate(c.options):
                pretty_print_schedule(schedule, index)
            print('')
    else:
        for c in classes:
            print(f'- {c.name}')


def generate_all_valid_choices(classes: list[Class], accepted: Hour_Range) -> list[list[Schedule]]:
    ranges = [range(len(c.options)) for c in classes]
    cartesian_product = itertools.product(*ranges)
    valid_choices = []

    for option_indices in cartesian_product:
        choice = [classes[class_index].options[option_index] 
                  for class_index, option_index in enumerate(option_indices)]
        if is_schedule_arrangement_valid(choice, accepted):
            valid_choices.append(choice)

    return valid_choices


def get_day_layout_div(valid_combination: list[Schedule]) -> html.Ul:
    root = html.Ul([])

    # Group schedules by the days they are active using the bit flags
    schedules_by_day = defaultdict(list)

    for schedule in valid_combination:
        for i in range(Day.Count):
            if schedule.days & (1 << i):
                schedules_by_day[i].append(schedule)

    # Iterate over each day and print its schedule
    for day_num in range(Day.Count):
        if day_num in schedules_by_day:
            schedules = schedules_by_day[day_num]
            day_str = DAYS_OF_WEEK[day_num]

            li = html.Li([])
            li.children.append(f"{day_str.capitalize()}:")

            # Sort schedules by their start time to display them in order
            schedules.sort(key=lambda x: (x.hours.start.hours, x.hours.start.minutes))

            ul = html.Ul([])
            for schedule in schedules:
                index = schedule.associated_class.options.index(schedule)
                class_name = schedule.associated_class.name
                time_range = str_from_hour_range(schedule.hours)
                in_person = "Presencial" if schedule.in_person else "Virtual"
                class_line =  [
                    f"{time_range}",
                    # f"(option_index={index:02d})",
                    f"Paralelo {schedule.group:02d}",
                    f"({in_person}, {schedule.available} cupos)",
                    f"{str_from_exam(schedule.exam)}: {class_name}",
                ]
                class_line = " ".join(class_line)
                ul.children.append(html.Li(class_line))
            li.children.append(ul)
            root.children.append(li)

    return root


def generate_class_color(class_index: int, total_classes: int) -> str:
    h = class_index / total_classes * 0.5
    r, g, b = colorsys.hsv_to_rgb(h, s=0.5, v=1.0)
    return f"rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)})"


def generate_time_slots(accepted: Hour_Range) -> list[str]:
    return [
        f"{h:02}:{m:02}"
        for h in range(accepted.start.hours, accepted.end.hours+1)
        for m in [0, 30] # half-hour intervals
    ]


def dataframe_from_valid_combination(
    valid_combination: list[tuple[Schedule]],
    accepted: Hour_Range,
) -> pd.DataFrame:
    time_slots = generate_time_slots(accepted)
    data = []

    # Initialize a dictionary for each day
    schedule_dict = {day: [""] * len(time_slots) for day in DAYS_OF_WEEK}

    for schedule in valid_combination:
        class_name = schedule.associated_class.name

        # Starting and end times in minutes
        start_time = schedule.hours.start.hours * 60 + schedule.hours.start.minutes
        end_time = schedule.hours.end.hours * 60 + schedule.hours.end.minutes

        # Find the corresponding rows for start and end times
        start_row = (start_time - accepted.start.hours * 60) // 30
        end_row = (end_time - accepted.start.hours * 60) // 30

        # Fill the schedule for the corresponding days
        for i in range(Day.Count):
            if schedule.days & (1 << i):
                day = DAYS_OF_WEEK[i]
                for row in range(start_row, end_row):
                    if schedule_dict[day][row] == "":
                        not_in_person = "(Virtual)" if not schedule.in_person else ""
                        schedule_dict[day][row] = f"{class_name} P{schedule.group} {not_in_person}"

    # Convert the schedule dictionary to a list of rows
    for time, row in zip(time_slots, range(len(time_slots))):
        data_row = [time] + [schedule_dict[day][row] for day in DAYS_OF_WEEK]
        data.append(data_row)

    # Create the DataFrame for easy table plotting
    df = pd.DataFrame(data, columns=["Time"] + DAYS_OF_WEEK)
    return df


def generate_color_grid(
    valid_combination: list[tuple[Schedule]],
    accepted: Hour_Range,
    classes: list[Class],
    classes_colors: list[str],
) -> dict[str, list[str]]:
    time_slots = generate_time_slots(accepted)

    color_dict = {day: [""] * len(time_slots) for day in DAYS_OF_WEEK}

    for schedule in valid_combination:
        class_index = classes.index(schedule.associated_class)

        # Starting and end times in minutes
        start_time = schedule.hours.start.hours * 60 + schedule.hours.start.minutes
        end_time = schedule.hours.end.hours * 60 + schedule.hours.end.minutes

        # Find the corresponding rows for start and end times
        start_row = (start_time - accepted.start.hours * 60) // 30
        end_row = (end_time - accepted.start.hours * 60) // 30

        for i in range(Day.Count):
            if schedule.days & (1 << i):
                day = DAYS_OF_WEEK[i]
                for row in range(start_row, end_row):
                    if color_dict[day][row] == "":
                        color_dict[day][row] = classes_colors[class_index]
    return color_dict


def generate_style(
    valid_combination: list[tuple[Schedule]],
    accepted: Hour_Range,
    classes: list[Class],
    classes_colors: list[str],
):
    color_dict = generate_color_grid(valid_combination, accepted, classes, classes_colors)
    style_conditions = []
    
    for day_str, rows in color_dict.items():
        day_index = DAYS_OF_WEEK.index(day_str)
        for row_index, color_str in enumerate(rows):
            if len(color_str) > 0:
                style_conditions.append({
                    'if': {
                        'column_id': DAYS_OF_WEEK[day_index],
                        'row_index': row_index,
                    },
                    'backgroundColor': color_str,
                    'color': 'black',  # Text color
                })
    
    return style_conditions


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

        show_classes = False; show_options = True
        if show_classes:
            print('-'*90)
            show_semester_line(prev_line, show_options)
            print('-'*90)
            show_semester_line(this_line, show_options)
            print('-'*90)

        classes = []
        classes.extend(prev_line)
        classes.append(this_line[0])
        # classes.append(this_line[1])
        classes.append(this_line[2])
        classes.append(this_line[3])

        classes_colors = [generate_class_color(i, len(classes)) for i in range(len(classes))]

        if show_classes:
            for i, c in enumerate(classes):
                print(f'[{i:02d}] = |option_count:{len(c.options):02d}| {c.name}')

        # TODO: Make the accepted hour range configurable
        accepted = hour_range_from_str('9:00-16:30')

        valid_combinations = generate_all_valid_choices(classes, accepted)
        dataframes = [dataframe_from_valid_combination(choice, accepted) for choice in valid_combinations]
        grid_styles = [generate_style(choice, accepted, classes, classes_colors) for choice in valid_combinations]
        day_layout_divs = [get_day_layout_div(choice) for choice in valid_combinations]

        idx = 0
        app = dash.Dash(__name__)
        root_style = {
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'fontSize': '14px',
            'fontFamily': 'Inter',
        }

        if len(valid_combinations) > 0:
            df = dataframes[idx]
            day_layout_div = day_layout_divs[idx]
            conditional_style = grid_styles[idx]

            app.layout = html.Div([
                html.Link(
                    rel='stylesheet',
                    href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap'
                ),

                dcc.Store(id='current-index', data=idx),

                html.P(id='current-schedule', children=f"Posibilidad #{idx+1} de {len(valid_combinations)}"),

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
                        'width': '70%',
                    },
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': '12px',
                        'fontFamily': 'Inter',
                        'height': 'auto',
                        'width': 'auto',
                    },
                    style_header={
                        'fontWeight': 'bold',
                        'backgroundColor': 'lightgray'
                    },
                    style_data_conditional=conditional_style,
                ),
            ], style=root_style)

            @app.callback(
                [
                    Output('current-index',    'data'),
                    Output('current-schedule', 'children'),
                    Output('schedule-layout',  'children'),
                    Output('schedule-table',   'data'),
                    Output('schedule-table',   'style_data_conditional'),
                ],
                [
                    Input('left-arrow-max',  'n_clicks'),
                    Input('left-arrow',      'n_clicks'),
                    Input('right-arrow',     'n_clicks'),
                    Input('right-arrow-max', 'n_clicks')
                ],
                [
                    State('current-index', 'data'),
                ]
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
                conditional_style = grid_styles[idx]
                current_schedule = f"Posibilidad #{idx+1} de {len(valid_combinations)}"

                # These need to line up with the `Output`s specified in @app.callback()
                return (
                    idx,
                    current_schedule,
                    day_layout_div,
                    df.to_dict('records'),
                    conditional_style,
                )
        else:
            app.layout = html.Div([
                html.Link(
                    rel='stylesheet',
                    href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap'
                ),
                html.P(f"No hay posibles combinaciones"),
            ], style=root_style)

        app.run(debug=True)


if __name__ == "__main__":
    main()
