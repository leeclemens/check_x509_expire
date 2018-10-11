#!/usr/bin/env python
"""
Generic check for monitoring a certificate's expiration date

MIT License

Copyright (c) 2016 Lee Clemens

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import print_function

import datetime
import re
import subprocess
import sys
import traceback

STATUS_OK = 0
STATUS_WARNING = 1
STATUS_CRITICAL = 2
STATUS_UNKNOWN = 3

PREFIXES = {
    STATUS_OK: 'OK',
    STATUS_WARNING: 'WARNING',
    STATUS_CRITICAL: 'CRITICAL',
    STATUS_UNKNOWN: 'UNKNOWN'
}


def usage():
    print('Usage: %s -s server -p port -w days -c days'
          ' [-t <protocol>]' % sys.argv[0])
    print('\t-s server      server name')
    print('\t-p port        port')
    print('\t-w days        warning threshold')
    print('\t-c days        critical threshold')
    print('\t-t proto       starttls protocol')
    sys.exit(STATUS_UNKNOWN)


def parse_args():
    args_dict = {
        'server': None,
        'port': None,
        'warning': None,
        'critical': None,
        'starttls': None,
    }
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-s':
            if i + 1 < len(sys.argv):
                i += 1
                args_dict['server'] = sys.argv[i]
            else:
                print('-s requires a value, server')
                usage()
        elif arg == '-p':
            if i + 1 < len(sys.argv):
                i += 1
                try:
                    args_dict['port'] = int(sys.argv[i])
                except ValueError:
                    print('-p port must be an integer')
                    usage()
            else:
                print('-p requires a value, port')
                usage()
        elif arg == '-w':
            if i + 1 < len(sys.argv):
                i += 1
                try:
                    args_dict['warning'] = int(sys.argv[i])
                except ValueError:
                    print('-w days must be an integer')
                    usage()
            else:
                print('-w requires a value, days')
                usage()
        elif arg == '-c':
            if i + 1 < len(sys.argv):
                i += 1
                try:
                    args_dict['critical'] = int(sys.argv[i])
                except ValueError:
                    print('-c days must be an integer')
                    usage()
            else:
                print('-c requires a value, days')
                usage()
        elif arg == '-t':
            if i + 1 < len(sys.argv):
                i += 1
                args_dict['starttls'] = sys.argv[i]
            else:
                print('-s requires a value, starttls protocol')
                usage()
        i += 1
    return args_dict


def run(server, port, warning, critical, starttls):
    # TODO: Use pipe-aware Popen calls
    openssl_cmd = 'echo' \
                  ' | openssl s_client -crlf %s-servername %s' \
                  ' -connect %s:%s 2>/dev/null' \
                  ' | openssl x509 -noout -dates' \
                  % ('-starttls %s ' % starttls if starttls else '',
                     server, server, port)
    proc = subprocess.Popen(openssl_cmd, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode == 0:
        regex = re.compile(r"^notBefore=(?P<before>(.*))\n"
                           r"notAfter=(?P<after>(.*))\n", re.MULTILINE)
        # TODO: Better py2-3 compatibility (no install, 2to3)
        match = regex.match(stdout
                            if isinstance(stdout, str)
                            else stdout.decode('utf-8'))
        if match:
            cert_date_format = "%b %d %H:%M:%S %Y %Z"
            before = datetime.datetime.strptime(match.group('before'),
                                                cert_date_format)
            after = datetime.datetime.strptime(match.group('after'),
                                               cert_date_format)
        else:
            print(stdout)
            print('Unexpected number of certificates')
            sys.exit(STATUS_CRITICAL)
        assert before is not None
        assert after is not None

        cur_time = datetime.datetime.utcnow()
        if before <= cur_time:
            if after >= cur_time:
                if after - cur_time <= datetime.timedelta(days=warning):
                    if after - cur_time <= datetime.timedelta(days=critical):
                        exit_with_perf_data(after, cur_time, STATUS_CRITICAL)
                    else:
                        exit_with_perf_data(after, cur_time, STATUS_WARNING)
                else:
                    exit_with_perf_data(after, cur_time, STATUS_OK)
            else:
                print('Certificate in no longer valid')
                exit_with_perf_data(after, cur_time, STATUS_CRITICAL)
        else:
            print('Certificate is not yet valid')
            exit_with_perf_data(after, cur_time, STATUS_CRITICAL, before)
    else:
        print('Failed to execute %s %s %s' %
              (openssl_cmd, stdout, stderr))
        sys.exit(STATUS_CRITICAL)


def exit_with_perf_data(after, cur_time, exit_code, before=None):
    time_remaining = after - cur_time
    if hasattr(time_remaining, 'total_seconds'):
        time_remaining_sec = time_remaining.total_seconds()
    else:
        time_remaining_sec = (time_remaining.microseconds + (
            time_remaining.seconds + time_remaining.days * 24 * 3600) *
                              10 ** 6) / 10 ** 6
    perf_data_days = time_remaining_sec / 60 / 60 / 24
    print('%s - Expires: %s%s | days_remaining=%s' % (
        PREFIXES[exit_code],
        after,
        ' Not valid until: %s' % before
        if before else '',
        perf_data_days))
    sys.exit(exit_code)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 1 or '-h' in sys.argv or '--help' in sys.argv:
            usage()
        else:
            ARGS = parse_args()
            if ARGS['server'] is None:
                print('Server must be provided')
                usage()
            if ARGS['port'] is None:
                print('Port must be provided')
                usage()
            if ARGS['warning'] is None:
                print('Warning days must be provided')
                usage()
            if ARGS['critical'] is None:
                print('Critical days must be provided')
                usage()
            if ARGS['warning'] < ARGS['critical']:
                print('Warning days must be greater than or equal'
                      ' to critical days')
                usage()
            run(ARGS['server'], ARGS['port'],
                ARGS['warning'], ARGS['critical'],
                ARGS['starttls'])
    # pylint: disable=broad-except
    except Exception as ex:
        print('%s: Unhandled exception %s' % (sys.argv[0], type(ex)))
        print(ex)
        traceback.print_exc()
        sys.exit(STATUS_CRITICAL)
