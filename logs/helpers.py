from config import constants


def tail(filename: str, n: int = constants.return_last_n_lines) -> list:
    """ Return last n lines from the file """

    try:
        with open(filename) as file:
            lines = file.readlines()

            if n >= len(lines):
                return lines

            return lines[len(lines) - n:]

    except IOError:
        raise ValueError('Specified file not found: {0}'.format(filename))


def process_log_strings(strings: list) -> list:
    """ Mark given lines like blocks with newlines and color """

    if strings is None:
        return []

    mark_as_red = False
    appended_string = ''
    processed_strings = []

    for string in strings:
        if len(string):
            if 'Received task' in string:
                mark_as_red = False
                string = '<br/>' + string

            if 'succeeded' in string:
                string = string + '<br/>'

            if 'ERROR' in string:
                mark_as_red = True

            if mark_as_red:
                string = '<font color="red">' + string + '</font>'

            appended_string += string + '<br/>'

        else:
            mark_as_red = False
            processed_strings.append(appended_string)
            appended_string = ''

    processed_strings.append(appended_string)
    return processed_strings
