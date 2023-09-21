#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Yet Another Pi Radio application.
This is a multi-mode radio app for a Pi, for streaming from the internet or from a TV Headend server
'''

import argparse
import configparser
import datetime
import json
import os
import re
#import stat
import signal
import sys
import subprocess
import time
from threading import Event, Thread
import select
import tty
import termios

import urllib
from http.server import HTTPServer, SimpleHTTPRequestHandler
import requests
from requests.auth import HTTPDigestAuth

# requires making code less readable:
# Xpylint:disable=bad-whitespace
# pylint:disable=too-many-branches
# pylint:disable=too-many-locals
# Xpylint:disable=too-many-nested-blocks
# Xpylint:disable=too-many-statements
# pylint:disable=global-statement
# pylint:disable=multiple-statements

# broken in pylint3:
# pylint:disable=global-variable-not-assigned

##########################################################################################

URL_GITHUB_HASH_SELF = 'https://api.github.com/repos/speculatrix/tvh_radio/tvh_radio.py'

GOOGLE_TTS = 'http://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q='
G_TTS_UA = 'VLC/3.0.2 LibVLC/3.0.2'

KEYBOARD_POLL_TIMEOUT = 0.5

# string constants
TS_URL_CHN = 'api/channel/grid'
TS_URL_STR = 'stream/channel'
TS_URL_PEG = 'api/passwd/entry/grid'
TS_MAX_CHANS = 1600 # don't fetch more than this number of channels

# name of Tvheadend Server parameters
TS_URL = 'ts_url'
TS_USER = 'ts_user'
TS_PASS = 'ts_pass'
TS_PAUTH = 'ts_pauth'
TS_AUTH_TYPE='ts_auth_type'         # digest or plain authentication
TS_CHN_LIMIT = 'ts_chn_lim'         # see TS_MAX_CHANS
TS_PROFILE = 'pass'                 # use audio-only or pass

PLAYER_COMMAND = 'player_command'

WEB_PORT = 'web_port'              # default web port, 0 to disable, 8080 suggested
WEB_PUBLIC = 'web_public'          # listen on all interfaces or localhost

TITLE = 'title'
DFLT = 'default'
HELP = 'help'


# the settings file is stored in a directory under $HOME
SETTINGS_DIR = '.tvh_radio'
SETTINGS_FILE = 'settings.ini'
SETTINGS_SECTION = 'user'
STREAMS_LIST = 'streams_list.dat'
FAVOURITES_LIST = 'favourites_list.dat'

STREAMS_HDR = '''# restart tvh_radio after making changes made to this file
# this is the streams list. hashes are comments.
# the stream name is on one line, the next line is the URL.'''

FAVOURITES_HDR = '''# DO NOT EDIT this file whilst tvh_radio is running!
# this is the favourites list. hashes are comments.
# the stream name is on one line, the next line is the URL.'''


SETTINGS_DEFAULTS = {
    TS_URL: {
        TITLE: 'URL',
        DFLT: 'http://tvh.example.com:9981',
        HELP: 'This is the URL of the TV Headend Server main web interface, ' \
              'without the trailing slash',
    },
    TS_CHN_LIMIT: {
        TITLE: '',
        DFLT: '1000',
        HELP: 'Limits the channels returned by TVHeadend when asking for a channel list',
    },
    TS_AUTH_TYPE: {
        TITLE:  'Authentication, digest or plain',
        DFLT:   'digest',
        HELP:   'avoid using plain unless you have a very good reason',
    },
    TS_USER: {
        TITLE: 'User',
        DFLT: TS_USER,
        HELP: 'This is a user with API access and streaming rights',
    },
    TS_PASS: {
        TITLE: 'Pass',
        DFLT: TS_PASS,
        HELP: 'Password on TVH server',
    },
    TS_PAUTH: {
        TITLE: 'P.A.T.',
        DFLT: TS_PAUTH,
        HELP: 'The Persistent Auth Token is used so the stream player doesn\'t need a ' \
              'a password, and can be found by logging into the TV headend, ' \
              'editing the user to set persistent auth on, then saving, then re-edit ' \
              'and scroll down to see the persistent auth value',
    },
    PLAYER_COMMAND: {
        TITLE: 'Player',
        DFLT: '/usr/bin/omxplayer.bin -o alsa --threshold 2',
        #DFLT: 'vlc -I dummy --novideo',
        HELP: 'Command to play media with arguments, try:\n'        \
              '"/usr/bin/omxplayer.bin -o alsa --threshold 2" or\n' \
              '"vlc -I dummy --novideo --play-and-exit"',
    },
    WEB_PORT: {
        TITLE: 'Web Port',
        DFLT: '8080',
        HELP: 'Web port (use 8080) or zero to disable',
    },
    WEB_PUBLIC: {
        TITLE:  'Web Public',
        DFLT:   '0',
        HELP:   'Set to 1 otherwise is localhost only',
    },
}


# Radio Modes
RM_TVH = 'TVH'      # tv headend channels
RM_STR = 'STR'      # streams list
RM_FAV = 'FAV'      # favourites list

RM_TEXT = {
        RM_TVH: 'TVHeadend',
        RM_STR: 'Stream List',
        RM_FAV: 'Favourites List',
}


# Chunks of text
HELP_TEXT = '''=== Help
? - help
d - down a channel
e - edit streams list
h - help
f - favourite or unfavourite a channel
F - favourites list
m - mode change - TVH, stream or favourites
p - play/stop channel
q - quit
s - speak current channel name
s - speak next channel name
t - speak time
u - up a channel
'''

VALID_WEB_COMMANDS = ('d', 'f', 'F', 'm', 'p', 's', 'S', 't', 'u', )

# web page head html with option to insert a string
WEB_HEAD = '''<html>
<head>
    <title>tvh_radio.py</title>
    <link rel="shortcut icon" type="image/png" href="%s"/>
    %s
</head>
'''

WEB_BODY = '''<body>
<h1>tvh_radio.py</h1>

<table border="0">
<tr>
    <td colspan="2" align="center"><a href="/">update page</a></td>
</tr>
%s
<tr>
    <td align="right"><a href='/u'><img src="/images/up.png" /></a></td>
    <td>up a channel</td>
</tr>

<tr>
    <td align="right"><a href='/d'><img src="/images/down.png" /></a></td>
    <td>down a channel</td>
</tr>

<tr>
    <td align="right"><a href='/p'><img src="/images/ball.red.png" /></a></td>
    <td>play/pause</td>
</tr>

<tr>
    <td align="right"><a href='/f'><img src="/images/image1.png" /></a></td>
    <td>favourite toggle</td>
</tr>
<tr>
    <td align="right"><a href='/m'><img src="/images/forward.png" /></a></td>
    <td>change mode</td>
</tr>
<tr>
    <td align="right"><a href='/s'><img src="/images/sound1.png" /></a></td>
    <td>speak the current channel name</td>
</tr>
<tr>
    <td align="right"><a href='/S'><img src="/images/sound1.png" /></a></td>
    <td>speak the future channel name</td>
</tr>
<tr>
    <td align="right"><a href='/t'><img src="/images/world2.png" /></a></td>
    <td>time and date</td>
</tr>
</table>

<hr>
More info here: <a href="https://github.com/speculatrix/tvh_radio" target="_new">github</a>
<br />
If you want to chromecast from TVH, try this: <a href="https://github.com/speculatrix/tvh_epg" target="_new">tvh_epg</a>
</body>
</html>
'''

####
# the nasty hack of having globals for threads to share data
GLOBALS = {}
# keys for the globals, hopefully to prevent typos, python will optimise
# these as reference by hash so it's not expensive
G_CHAN_NAME_FUTURE = 'channel name future'
G_CHAN_NUM_FUTURE = 'channel number future'
G_CHAN_NAME_PLAYING = 'channel name playing'
G_DBG_LEVEL     = 'debug_level'
G_EVENT         = 'event handler'
G_KEY_STROKE    = 'key_stroke'
G_MY_SETTINGS   = 'my settings'
G_PLAYER_PID    = 'player_pid'
G_QUIT_FLAG     = 'quit_flag'
G_RADIO_MODE    = 'radio_mode'
G_STOP_PLAYBACK = 'stop playback'


##########################################################################################
# help
def print_help():
    ''' prints help '''

    print(HELP_TEXT)

##########################################################################################
def api_test_func():
    ''' secret function for testing the TVH API in various ways '''

    global GLOBALS

    ts_url = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_URL]
    ts_auth_type = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_AUTH_TYPE]
    ts_user = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_USER]
    ts_pass = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s' % (
        ts_url,
        TS_URL_PEG,
    )

    if ts_auth_type == 'plain':
        ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    else:
        ts_response = requests.get(ts_query, auth=HTTPDigestAuth(ts_user, ts_pass))

    print('<!-- api_test_func URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return

    ts_json = ts_response.json()
    #if GLOBALS[G_DBG_LEVEL] > 0:
    print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )


##########################################################################################
def streams_editor():
    ''' function to invoke external editor on streams list '''

    print('=== Streams List Editor ===')
    print('Please edit the file %s with your favourite editor' %
          (os.path.join(os.environ['HOME'], SETTINGS_DIR, STREAMS_LIST), ))

##########################################################################################
def channel_editor(chan_map):
    ''' unused but an idea for a very simple channel editor '''

    print('=== Channel Editor ===')

    print('a - add channel')
    print('d - delete channel')
    print('e - exit and save')
    print('l - list')
    print('q - quit without saving')

    cmd =''
    while cmd not in [ 'e', 'q', ]:
        cmd = input('? ')
        if cmd == 'a':
            print('Channel name to add: ')
            print('Channel url to add: ')
            #if chan_add(chan_map):
                #max_chan = len(chan_map)
        elif cmd == 'd':
            #chan_del(chan_map)
            print('Number of channel to delete: ')
        elif cmd == 'l':
            print_channel_list('\t', chan_map)


##########################################################################################
def print_channel_list(prefix, chan_list):
    ''' prints a channel list, with the prefix being an arbitrary string starting
        each line, so use '\t' or ' ' for example
    '''

    for (chan_name, chan_url) in chan_list.items():
        print("%s%s : %s" % (prefix, chan_name, chan_url, ))


##########################################################################################
def write_list_file(text_header, file_name, list_data):
    ''' writes the data file which is a streams list or a favourites list

    prints the text header, which is usually a comment

    lines are then paired, the first is the name of the stream, the second is the URL

    returns True or False on Success or Failure
    '''

    if not list_data:
        return False

    fh_list = open(file_name, 'w')
    if not fh_list:
        print('Error, streams listing file %s was unwritable' % (file_name, ))
        return False

    fh_list.write(text_header)
    fh_list.write('\n')

    for (stream_name, stream_url) in list_data.items():
        fh_list.write(stream_name)
        fh_list.write('\n')
        fh_list.write(stream_url)
        fh_list.write('\n')

    fh_list.close()
    return True

##########################################################################################
def read_list_file(file_name):
    ''' reads the data file which is a streams list or a favourites list

    first line is just some help text
    lines are then paired, the first is the name of the stream, the second is the URL

    returns a dict, with the key being the stream name
    '''

    if not os.path.isfile(file_name):
        print('Warning, streams listing file %s nonexistent' % (file_name, ))
        return {}

    list_data = {}
    #print('Debug, attempting to open and read lines from %s' % (file_name, ))

    fh_list = open(file_name, 'r')
    if not fh_list:
        print('Error, streams listing file %s was unreadable or missing' % (file_name, ))
        return list_data

    # simple state machine based on the previous line read
    # read lines, skip over comments, and any two non-comment lines are
    # assumed to be stream name then stream URL
    next_line = '#'
    prev_line = '#'
    while next_line != '':
        next_line = fh_list.readline().strip()
        # exit on a blank line
        if next_line == '':
            break

        # skip over comments until we have two non-comment lines
        if next_line[0] == '#' or prev_line[0] == '#':
            prev_line = next_line
            continue

        if prev_line != '' and next_line != '':
            #print('Found %s  ==>> %s' % (prev_line, next_line, ))
            list_data[prev_line] = next_line
            next_line = '#'     # start searching again

        prev_line = next_line

    fh_list.close()
    return dict(sorted(list_data.items()))

##########################################################################################
def text_to_speech_file(input_text, output_file):
    ''' uses Google to turn supplied text into speech in the file '''

    goo_url = '%s%s' % (GOOGLE_TTS, urllib.parse.quote(input_text), )
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-agent', G_TTS_UA), ]

    write_handle = open(output_file, 'wb')
    with opener.open(goo_url) as goo_handle:
        write_handle.write(goo_handle.read())


##########################################################################################
def chan_data_to_tts_file(chan_name):
    ''' given the channel data, returns the name of a sound file which is the
        channel name; calls text_to_speech_file to generate it if required '''

    global GLOBALS

    tts_file_name = '%s.mp3' % (os.path.join(os.environ['HOME'], SETTINGS_DIR, chan_name), )

    if not os.path.isfile(tts_file_name):
        text_to_speech_file(chan_name, tts_file_name)

    return tts_file_name


##########################################################################################
def get_tvh_chan_urls():
    ''' gets the channel listing and generates an ordered dict
        returns dict: key = channel name, value = stream URL
    '''

    global GLOBALS

    ts_url = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_URL]
    ts_auth_type = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_AUTH_TYPE]
    ts_user = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_USER]
    ts_pass = GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s?limit=%s' % (
        ts_url,
        TS_URL_CHN,
        GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_CHN_LIMIT],
    )

    if ts_auth_type == 'plain':
        ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    else:
        ts_response = requests.get(ts_query, auth=HTTPDigestAuth(ts_user, ts_pass))

    print('<!-- get_tvh_chan_urls URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return {}

    ts_json = ts_response.json()
    if GLOBALS[G_DBG_LEVEL] > 1:
        print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    if TS_PAUTH in GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION]:
        ts_pauth = '&AUTH=%s' % (GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_PAUTH], )
    else:
        ts_pauth = ''


    chan_map = {}  #  channel-name =>stream-url
    if 'entries' in ts_json:
        # grab all channel info
        name_unknown = 0
        #number_unknown = -1
        for entry in ts_json['entries']:
            # start building a dict with channel name as key
            if 'name' in entry:
                if 'name-not-set' in entry['name']:
                    #chan_name = str(entry['number'])   # number not unique
                    chan_name = 'uuid-' + entry['uuid']
                else:
                    chan_name = entry['name']
            else:
                chan_name = 'unknown ' + str(name_unknown)
                name_unknown += 1

            chan_map[chan_name] = '%s/%s/%s?profile=%s%s' % \
                                  (GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_URL],
                                   TS_URL_STR,
                                   entry['uuid'],
                                   TS_PROFILE,
                                   ts_pauth, )

    if GLOBALS[G_DBG_LEVEL] > 0:
        print('%s' % json.dumps(chan_map, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    return dict(sorted(chan_map.items()))


##########################################################################################
def check_load_config_file(settings_dir, settings_file):
    '''check there's a config file which is writable;
       returns 0 if OK, -1 if the rest of the page should be aborted,
       > 0 to trigger rendering of the settings page'''

    global GLOBALS

    ########
    if os.path.isfile(settings_dir):
        error_text = 'Error, "%s" is a file and not a directory' % (settings_dir, )
        return (-2, error_text)

    if not os.path.isdir(settings_dir):
        os.mkdir(settings_dir)
        if not os.path.isdir(settings_dir):
            error_text = 'Error, "%s" is not a directory, couldn\'t make it one' % (settings_dir, )
            return (-2, error_text)


    # verify the settings file exists and is writable
    if not os.path.isfile(settings_file):
        error_text = 'Error, can\'t open "%s" for reading' % (settings_file, )
        return(-1, error_text)

    # file is zero bytes?
    config_stat = os.stat(settings_file)
    if config_stat.st_size == 0:
        error_text = 'Error, "%s" file is empty\n' % (settings_file, )
        return(-1, error_text)

    if not GLOBALS[G_MY_SETTINGS].read(settings_file):
        error_text = 'Error, failed parse config file "%s"' % (settings_file, )
        return(-1, error_text)

    #print('Debug, check_load_config_file TVH url is %s'
    #      % (GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_URL], ) )

    return (0, 'OK')



##########################################################################################
# settings_editor
def settings_editor(settings_file):
    ''' settings_editor '''

    global GLOBALS

    if SETTINGS_SECTION not in GLOBALS[G_MY_SETTINGS].sections():
        print('section %s doesn\'t exit' % SETTINGS_SECTION)
        GLOBALS[G_MY_SETTINGS].add_section(SETTINGS_SECTION)

    print('=== Settings ===')

    # attempt to find the value of each setting, either from the params
    # submitted by the browser, or from the file, or from the defaults
    for setting in SETTINGS_DEFAULTS:
        setting_value = ''

        try:
            setting_value = str(GLOBALS[G_MY_SETTINGS].get(SETTINGS_SECTION, setting))
        except configparser.NoOptionError:
            if DFLT in SETTINGS_DEFAULTS[setting]:
                setting_value = SETTINGS_DEFAULTS[setting][DFLT]
            else:
                setting_value = ''

        # one day the settings editor will be more clever
        #print('type of %s is %s' % (setting, type(setting)))
        print('Hint: %s' % (SETTINGS_DEFAULTS[setting][HELP], ))
        print('%s [%s]: ' % (SETTINGS_DEFAULTS[setting][TITLE], setting_value, ), end='')
        sys.stdout.flush()
        new_value = sys.stdin.readline().rstrip()
        if new_value not in ('', '\n'):
            GLOBALS[G_MY_SETTINGS].set(SETTINGS_SECTION, setting, new_value)
        else:
            GLOBALS[G_MY_SETTINGS].set(SETTINGS_SECTION, setting, setting_value)
        print('')

    config_file_handle = open(settings_file, 'w')
    if config_file_handle:
        GLOBALS[G_MY_SETTINGS].write(config_file_handle)
    else:
        print('Error, failed to open and write config file "%s"' %
              (settings_file, ))
        sys.exit(1)


##########################################################################################
def play_time():
    ''' writes the time and date into temp file and calls Google TTS to speak it '''

    now = datetime.datetime.now()
    the_time_is = now.strftime('the time is %M minutes past %H, on %b %d, %Y')
    time_file = os.path.join(os.path.join(os.environ['HOME'], SETTINGS_DIR, 'time_file.mp3'))
    text_to_speech_file(the_time_is, time_file)
    play_file(time_file)


##########################################################################################
def play_file(audio_file_name):
    ''' plays a local audio file '''

    global GLOBALS

    play_cmd = GLOBALS[G_MY_SETTINGS].get(SETTINGS_SECTION, PLAYER_COMMAND)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(audio_file_name)
    #print('Debug, play command is "%s"' % ('" "'.join(play_cmd_array), ))

    subprocess.call(play_cmd_array)


##########################################################################################
# play_channel
def play_channel(stream_url):
    ''' starts playing stream in a sub process
        if it sees STOP_PLAYBACK then it kills the player '''

    global GLOBALS

    url = stream_url

    play_cmd = GLOBALS[G_MY_SETTINGS].get(SETTINGS_SECTION, PLAYER_COMMAND)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(url)
    print('Debug, play command is "%s"' % ('" "'.join(play_cmd_array), ))

    player_proc = subprocess.Popen(play_cmd_array, shell=False)
    GLOBALS[G_PLAYER_PID] = player_proc.pid
    if GLOBALS[G_DBG_LEVEL]: print('Debug, player pid %d' % (player_proc.pid, ))

    player_active = True

    # we check every second if the player is running or told to kill it
    while player_active:
        try:
            # poll for playback process to end
            player_proc.wait(timeout=1)
            # only gets here if playback process ended
            #print('Debug, player finished')
            player_active = False
            GLOBALS[G_STOP_PLAYBACK] = False
            GLOBALS[G_PLAYER_PID] = 0

        # if the player is still running this exception is called
        except subprocess.TimeoutExpired:
            pass
            #print('Debug, player still running')

        # kill the player on demand
        if GLOBALS[G_STOP_PLAYBACK]:
            #print('Debug, killing player process')
            player_proc.kill()

    print('play_channel exiting')
    GLOBALS[G_CHAN_NAME_PLAYING] = ''

##########################################################################################
# SIGINT/ctrl-c handler
def sigint_handler(_signal_number, _frame):
    ''' called when signal 2 or CTRL-C hits process, simply flags request to quit '''

    global GLOBALS

    print('\nCTRL-C QUIT')
    GLOBALS[G_QUIT_FLAG] = True
    GLOBALS[G_EVENT].set()


##########################################################################################
def keyboard_listen_thread():
    ''' keyboard listening thread, sets raw input and uses sockets to
        get single key strokes without waiting, triggering an event. '''

    global GLOBALS

    # set term to raw, so doesn't wait for return
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    while GLOBALS[G_QUIT_FLAG] == 0:
        # a bit ugly, but use a timeout just to occasionally check QUIT_FLAG
        readable_sockets, _o, _e = select.select([sys.stdin], [], [], KEYBOARD_POLL_TIMEOUT)
        if readable_sockets:
            GLOBALS[G_KEY_STROKE] = sys.stdin.read(1)
            GLOBALS[G_EVENT].set()

    # set term back to cooked
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


##########################################################################################
def save_favourites(list_data):
    ''' saves the current favourites to a file '''

    write_list_file(FAVOURITES_HDR,
                    os.path.join(os.environ['HOME'], SETTINGS_DIR, FAVOURITES_LIST),
                    list_data)

##########################################################################################
class MyHTTPRequestHandler(SimpleHTTPRequestHandler):
    ''' minimal http request handler for remote control '''

    global GLOBALS

    def do_GET(self):   # pylint:disable=invalid-name
        ''' implement the http GET method '''

        global GLOBALS

        uri_get_regex = re.compile(r'GET (.*) HTTP.*')
        re_matches = uri_get_regex.match(self.requestline)
        if re_matches:
            uri = re_matches.group(1)
        else:
            uri = '/'	# fallback, but it should never get here

        if '.png' in uri:
            print('Debug, attempting to send image')
            SimpleHTTPRequestHandler.do_GET(self)
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            print('Debug, executing command and sending status')
            # miss off the leading /
            if uri[1:] in VALID_WEB_COMMANDS:
                GLOBALS[G_KEY_STROKE] = uri[1:]
                GLOBALS[G_EVENT].set()
                time.sleep(0.5)
                # refresh after entering a command, not too quickly as the
                # user might be quickly changing channels
                extra_header = '  <meta http-equiv="refresh" content="3;/">'
            else:
                extra_header = ''

            favicon_url = '%s/favicon.ico' % (GLOBALS[G_MY_SETTINGS][SETTINGS_SECTION][TS_URL], )
            self.wfile.write(bytearray(WEB_HEAD % (favicon_url, extra_header, ), encoding='ascii'))

            if GLOBALS[G_PLAYER_PID] != 0:
                if GLOBALS[G_STOP_PLAYBACK]:
                    status_playing = '<tr><td align="right">playing</td>'   \
                                     '<td>%s but stopping soon</td></tr>\n' \
                                     % GLOBALS[G_CHAN_NAME_PLAYING]
                else:
                    status_playing = '<tr><td align="right">playing</td>'   \
                                     '<td>%s</td></tr>\n' % GLOBALS[G_CHAN_NAME_PLAYING]
            else:
                status_playing = ''

            if GLOBALS[G_CHAN_NAME_FUTURE] != '':
                channel_future = '<tr><td align="right">playing in future</td>' \
                                 '<td>%s</td></tr>\n' % GLOBALS[G_CHAN_NAME_FUTURE]
            else:
                channel_future = ''

            radio_mode = '<tr><td align="right">radio mode</td>'    \
                         '<td>%s</td></tr>' % (RM_TEXT[GLOBALS[G_RADIO_MODE]], )
            status_complete = '%s%s%s' % (radio_mode, status_playing, channel_future, )

            self.wfile.write(bytearray(WEB_BODY % (status_complete, ), encoding='ascii'))

##########################################################################################
#def start_web_listener(wport, bind_host):
def start_web_listener(httpd):
    ''' a very primitive web interface for remote control '''

    global GLOBALS

    print('Debug. starting httpd server')
    httpd.serve_forever()   # never returns


##########################################################################################
def radio_app():
    '''this runs the radio appliance'''

    global GLOBALS

    # read the streams file into a boringly simple dict
    streams_chan_map = read_list_file(os.path.join(os.environ['HOME'],
                                                   SETTINGS_DIR, STREAMS_LIST))
    if streams_chan_map:
        print('There are %d streams' % (len(streams_chan_map), ))

    # get the favourites; if favourites are empty change the default
    # mode to TVH from favourites
    favourites_chan_map = read_list_file(os.path.join(os.environ['HOME'],
                                                      SETTINGS_DIR, FAVOURITES_LIST))
    if favourites_chan_map:
        print('There are %d favourites' % (len(favourites_chan_map), ))
    else:
        GLOBALS[G_RADIO_MODE] = RM_TVH

    # get the TVH channel map into the same format dict as the streams and favourites
    tvh_chan_map = get_tvh_chan_urls()

    if GLOBALS[G_RADIO_MODE] == RM_TVH:
        print('tvh radio mode')
        chan_map = tvh_chan_map
    elif GLOBALS[G_RADIO_MODE] == RM_STR:
        print('streaming radio mode')
        chan_map = streams_chan_map
    elif GLOBALS[G_RADIO_MODE] == RM_FAV:
        print('favourites radio mode')
        chan_map = favourites_chan_map
    else:
        print('Error, invalid radio mode')
        sys.exit(1)

    # sort and count channels for whatever mode we're in
    chan_names = list(chan_map.keys())  # get an indexable array
    max_chan = len(chan_map)            # max channel number

    chan_num = 0                        # start at first channel
    GLOBALS[G_CHAN_NUM_FUTURE] = chan_num
    GLOBALS[G_CHAN_NAME_FUTURE] = chan_names[chan_num]

    ####
    # now we have the data, lets do the radio thing!

    # trap ctrl-x/sigint so we can clean up
    signal.signal(signal.SIGINT, sigint_handler)

    # handles on the threads
    threads = {}

    # start a thread to listen to the keyboard
    threads['KB'] = Thread(target=keyboard_listen_thread)
    threads['KB'].start()

    # do we need to start a thread to act as the web server?
    if GLOBALS[G_MY_SETTINGS].get(SETTINGS_SECTION, WEB_PUBLIC) == '1':
        bind_host = ''
    else:
        bind_host = 'localhost'
    wport = GLOBALS[G_MY_SETTINGS].get(SETTINGS_SECTION, WEB_PORT)
    if wport and wport != '' and wport.isnumeric():
        httpd = HTTPServer((bind_host, int(wport)), MyHTTPRequestHandler)
        threads['WWW'] = Thread(target=start_web_listener, args=(httpd, ))
        threads['WWW'].start()

    print('Playing next: %s' % (GLOBALS[G_CHAN_NAME_FUTURE], ))
    # SIGINT and keyboard strokes and (one day) GPIO events all get funnelled here
    while not GLOBALS[G_QUIT_FLAG]:
        GLOBALS[G_EVENT].wait() # Blocks until the flag becomes true.
        if GLOBALS[G_KEY_STROKE] != '':
            if GLOBALS[G_KEY_STROKE] == 'A':   # secret key code :-)
                api_test_func()

            elif GLOBALS[G_KEY_STROKE] in ('?', 'h'):
                print_help()

            #elif GLOBALS[G_KEY_STROKE] == 'l':
                #GLOBALS[G_DBG_LEVEL] and print('list')
                #print('list')
                #print(', '.join(chan_names))

            elif GLOBALS[G_KEY_STROKE] == 'd':
                #GLOBALS[G_DBG_LEVEL] and print('down')
                if GLOBALS[G_DBG_LEVEL]: print('down')
                if chan_num > 0:
                    chan_num = chan_num - 1

            elif GLOBALS[G_KEY_STROKE] == 'e':
                if GLOBALS[G_DBG_LEVEL]: print('e')
                streams_editor()

            elif GLOBALS[G_KEY_STROKE] == 'E':
                if GLOBALS[G_DBG_LEVEL]: print('E')
                channel_editor(chan_map)
                #max_chan = len(chan_map)
                #chan_names = list(chan_map.keys())  # get an indexable array

            elif GLOBALS[G_KEY_STROKE] == 'f':
                if GLOBALS[G_DBG_LEVEL]: print('favourite')
                if chan_names[chan_num] in favourites_chan_map:
                    print('Removing channel %s to favourites' % (chan_names[chan_num], ))
                    del favourites_chan_map[chan_names[chan_num]]
                else:
                    print('Adding channel %s to favourites' % (chan_names[chan_num], ))
                    favourites_chan_map[chan_names[chan_num]] = chan_map[chan_names[chan_num]]
                    favourites_chan_map = dict(sorted(favourites_chan_map.items()))
                # re-count the channels
                if GLOBALS[G_RADIO_MODE] == RM_FAV:
                    max_chan = len(chan_map)
                    chan_names = list(chan_map.keys())  # get an indexable array

                save_favourites(favourites_chan_map)

            elif GLOBALS[G_KEY_STROKE] == 'F':
                if GLOBALS[G_DBG_LEVEL]: print('F')
                if favourites_chan_map:
                    print('Favourites:')
                    print_channel_list('\t', favourites_chan_map)
                else:
                    print('Warning, no favourites set')


            elif GLOBALS[G_KEY_STROKE] == 'm':
                if GLOBALS[G_DBG_LEVEL]: print('mode')
                # if changing mode, kill a running player
                while GLOBALS[G_PLAYER_PID] != 0:
                    print('Waiting to stop playback before changing mode')
                    GLOBALS[G_STOP_PLAYBACK] = True
                    time.sleep(1)

                # cycle between modes and choose the channel map for new mode
                if GLOBALS[G_RADIO_MODE] == RM_TVH:
                    GLOBALS[G_RADIO_MODE] = RM_STR
                    chan_map = streams_chan_map

                elif GLOBALS[G_RADIO_MODE] == RM_STR:
                    GLOBALS[G_RADIO_MODE] = RM_FAV
                    chan_map = favourites_chan_map

                elif GLOBALS[G_RADIO_MODE] == RM_FAV:
                    GLOBALS[G_RADIO_MODE] = RM_TVH
                    chan_map = tvh_chan_map
                else:
                    print('Error, mode change went wrong!')

                print('Debug, mode is now %s' % (GLOBALS[G_RADIO_MODE],))
                chan_num = 0                        # start at first channel
                chan_names = list(chan_map.keys())  # get an indexable array
                max_chan = len(chan_map)            # max channel number


            elif GLOBALS[G_KEY_STROKE] == 'p':
                if GLOBALS[G_DBG_LEVEL]: print('play')
                if GLOBALS[G_PLAYER_PID] != 0:
                    print('Setting STOP_PLAYBACK true')
                    GLOBALS[G_STOP_PLAYBACK] = True
                    # wait for the sub process to finish, ugly polling hack!
                    while GLOBALS[G_PLAYER_PID] != 0:
                        print('Info, waiting to stop playback')
                        time.sleep(1)
                    # playback has finished
                    threads['PB'].join()
                    del threads['PB']
                else:
                    GLOBALS[G_CHAN_NAME_PLAYING] = chan_names[chan_num]
                    print('attempting to play channel %d/%s' % (chan_num, chan_names[chan_num],))
                    stream_url = chan_map[chan_names[chan_num]]
                    threads['PB'] = Thread(target=play_channel, args=(stream_url, ))
                    threads['PB'].start()

            elif GLOBALS[G_KEY_STROKE] == 'q':
                print('Quit!')
                GLOBALS[G_QUIT_FLAG] = 1
                GLOBALS[G_STOP_PLAYBACK] = True
                if GLOBALS[G_PLAYER_PID] != 0:
                    # wait for the sub process to finish, ugly polling hack!
                    while GLOBALS[G_PLAYER_PID] != 0:
                        print('Info, waiting to stop playback')
                        time.sleep(1)
                    # playback has finished
                    threads['PB'].join()
                    del threads['PB']

            elif GLOBALS[G_KEY_STROKE] == 's':
                if GLOBALS[G_CHAN_NAME_PLAYING]:
                    tts_file = chan_data_to_tts_file(GLOBALS[G_CHAN_NAME_PLAYING])
                    play_file(tts_file)
                else:
                    print('Debug, not playing a channel so not speaking it\'s name')

            elif GLOBALS[G_KEY_STROKE] == 'S':
                print('Debug, speaking future channel name %s' % (GLOBALS[G_CHAN_NAME_FUTURE], ))
                tts_file = chan_data_to_tts_file(GLOBALS[G_CHAN_NAME_FUTURE])
                play_file(tts_file)

            elif GLOBALS[G_KEY_STROKE] == 't':
                play_time()

            elif GLOBALS[G_KEY_STROKE] == 'u':
                if GLOBALS[G_DBG_LEVEL]: print('up')
                if chan_num < max_chan - 1:
                    chan_num = chan_num + 1

            elif GLOBALS[G_KEY_STROKE] == 'm':
                if GLOBALS[G_RADIO_MODE] == RM_TVH:
                    GLOBALS[G_RADIO_MODE] = RM_STR
                else:
                    GLOBALS[G_RADIO_MODE] = RM_TVH
                    get_tvh_chan_urls()
                print(f'Mode now { GLOBALS[G_RADIO_MODE] }')

            else:
                print('Unknown key')

            GLOBALS[G_KEY_STROKE] = ''
        else:
            print('Error, unknown command key "%s"' % (GLOBALS[G_KEY_STROKE],))

        GLOBALS[G_CHAN_NUM_FUTURE] = chan_num
        GLOBALS[G_CHAN_NAME_FUTURE] = chan_names[chan_num]
        GLOBALS[G_EVENT].clear() # Resets the flag.
        print(f'Current channel: { G_CHAN_NAME_PLAYING }')
        print(f'Future channel: { GLOBALS[G_CHAN_NAME_FUTURE] }')

    if httpd:
        print('Waiting for web service to shut down')
        httpd.shutdown()
        time.sleep(1)

    for thread_name in threads:
        print(f'Debug, joining thread { thread_name } to this')
        threads[thread_name].join()


##########################################################################################
def main():
    '''the main entry point'''

    global GLOBALS

    # settings_file is the fully qualified path to the settings file
    settings_dir = os.path.join(os.environ['HOME'], SETTINGS_DIR)
    settings_file = os.path.join(settings_dir, SETTINGS_FILE)
    (config_bad, error_text) = check_load_config_file(settings_dir, settings_file)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', required=False,
                        action="store_true", help='increase the debug level')
    parser.add_argument('-s', '--setup', required=False,
                        action="store_true", help='run the setup process')
    args = parser.parse_args()

    if args.debug:
        GLOBALS[G_DBG_LEVEL] += 1
        print(f'Debug, increased debug level to { GLOBALS[G_DBG_LEVEL] }')

    if args.setup or config_bad < 0:
        if config_bad < -1:
            print('Error, severe problem with settings, please fix and restart program')
            print(f'{ error_text}')
            sys.exit(1)
        if config_bad < 0:
            print(f'{ error_text}')
        settings_editor(settings_file)
    else:
        radio_app()


##########################################################################################

if __name__ == "__main__":

    # initialise all globals
    GLOBALS[G_CHAN_NUM_FUTURE]  = 0         # the channel chosen but not playing
    GLOBALS[G_CHAN_NAME_PLAYING] = ''       # the channel currently playing
    GLOBALS[G_DBG_LEVEL]        = 0         #
    GLOBALS[G_EVENT]            = Event()   # global event handler
    GLOBALS[G_KEY_STROKE]       = ''        # no key been pressed
    GLOBALS[G_MY_SETTINGS]      = configparser.ConfigParser() # configuration are global
    GLOBALS[G_PLAYER_PID]       = 0         # not playing
    GLOBALS[G_QUIT_FLAG]        = False     # quit not triggered
    GLOBALS[G_RADIO_MODE]       = RM_FAV    # default
    GLOBALS[G_STOP_PLAYBACK]    = False     # playback stop triggered

    main()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
