import mmap
from os.path import getsize
from os import name as os_name


def tail(filename, n=50):
    """ Returns last n lines from the file """

    try:
        size = getsize(filename)

    except IOError:
        raise ValueError('Specified file not found: {0}'.format(filename))

    with open(filename, 'rb') as file:
        if os_name == 'nt':
            # Windows mmap

            filemap = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        else:
            # *nix mmap

            filemap = mmap.mmap(file.fileno(), 0, mmap.MAP_SHARED, mmap.PROT_READ)

        try:
            i = 0

            for i in range(size - 1, -1, -1):
                if filemap[i] == '\n':
                    n -= 1

                    if n == -1:
                        break

            return [str(string)[2:-1] for string in filemap[i + 1 if i else 0:].splitlines()]

        finally:
            filemap.close()


def process_log_strings(strings):
    """ Mark given lines like blocks with newlines and color """

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

    return processed_strings
