#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Yet Another Pi Radio application.
This is a multi-mode radio app for a Pi, for streaming from the internet or from a TV Headend server
'''

import argparse
import configparser
#import copy
import datetime
#import hashlib
import json
import os
#import stat
import signal
import sys
import subprocess
import time
from threading import Event, Thread
import select
import tty
#import collections
import termios

import urllib
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# requires making code less readable:
# Xpylint:disable=bad-whitespace
# pylint:disable=too-many-branches
# pylint:disable=too-many-locals
# Xpylint:disable=too-many-nested-blocks
# Xpylint:disable=too-many-statements
# pylint:disable=global-statement

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

TS_URL = 'ts_url'
TS_USER = 'ts_user'
TS_PASS = 'ts_pass'
TS_PAUTH = 'ts_pauth'
TS_PLAY = 'ts_play'

TS_WPORT = 'ts_wport'          # default web port, 0 to disable, 8080 suggested

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
        HELP: 'The Persistent Auth Token can be found by logging into the TV headend, ' \
              'editing the user to set persistent auth on, then saving, then re-edit ' \
              'and scroll down to see the persistent auth value',
    },
    TS_PLAY: {
        TITLE: 'Player',
        DFLT: '/usr/bin/omxplayer.bin -o alsa',
        #DFLT: 'vlc -I dummy --novideo',
        HELP: 'Command to play media with arguments, try "/usr/bin/omxplayer.bin -o ' \
               'alsa" or "vlc -I dummy --novideo --play-and-exit"',
    },
    TS_WPORT: {
        TITLE: 'Web Port',
        DFLT: '8080',
        HELP: 'Web port (use 8080) or zero to disable',
    },
 }


# Radio Modes
RM_TVH = 'TVH'      # tv headend channels
RM_STR = 'STR'      # streams list
RM_FAV = 'FAV'      # favourites list
RADIO_MODE = RM_FAV # default

RM_TEXT = {
        RM_TVH: 'TVHeadend',
        RM_STR: 'Stream List',
        RM_FAV: 'Favourites List',
}


valid_web_commands = ('d', 'f', 'm', 'p', 's', 't', 'u', )

# Chunks of text
HELP_TEXT = '''=== Help
? - help
d - down a channel
e - edit streams list
h - help
f - favourite or unfavourite a channel
m - mode change - TVH, stream or favourites
p - play/stop channel
q - quit
s - speak channel name
t - speak time
u - up a channel
'''

WEB_HOME = '''<html>
<head>
    <title>tvh_radio.py</title>
    <link rel="shortcut icon" type="image/png" href="%s"/>
    </head>
<body>
<h1>tvh_radio.py</h1>
%s
<a href='/'>update page</a>
<br />
<a href='/f'>favourite toggle</a>
<br />
<a href='/m'>change mode</a>
<br />
<a href='/p'>play/pause</a>
<br />
<a href='/d'>down a channel</a>
<br />
<a href='/u'>up a channel</a>
<br />

<hr>
More info here: <a href="https://github.com/speculatrix/tvh_radio" target="_new">github</a>
<br />
If you want to chromecast from TVH, try this: <a href="https://github.com/speculatrix/tvh_epg" target="_new">tvh_epg</a>
</body>
</html>
'''


##########################################################################################
# help
def print_help():
    ''' prints help '''

    print(HELP_TEXT)

##########################################################################################
def api_test_func():
    ''' secret function for testing the TVH API in various ways '''

    global DBG_LEVEL

    ts_url = MY_SETTINGS[SETTINGS_SECTION][TS_URL]
    ts_user = MY_SETTINGS[SETTINGS_SECTION][TS_USER]
    ts_pass = MY_SETTINGS[SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s' % (
        ts_url,
        TS_URL_PEG,
    )
    ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    print('<!-- api_test_func URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return

    ts_json = ts_response.json()
    #if DBG_LEVEL > 0:
    print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )


##########################################################################################
def streams_editor():
    ''' function to invoke external editor on streams list '''

    print('=== Streams List Editor ===')
    print('Please edit the file %s with your favourite editor' %
          (os.path.join(os.environ['HOME'], SETTINGS_DIR, STREAMS_LIST), ))

##########################################################################################
def print_channel_list(prefix, chan_list):
    ''' prints a channel list '''

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
    opener.addheaders =[('User-agent', G_TTS_UA), ]

    write_handle = open(output_file, 'wb')
    with opener.open(goo_url) as goo_handle:
        write_handle.write(goo_handle.read())


##########################################################################################
def chan_data_to_tts_file(chan_data):
    '''given the channel data, returns the name of a sound file which is the
       channel name; calls text_to_speech_file to generate it if required'''

    global DBG_LEVEL
    global MY_SETTINGS

    tts_file_name = '%s.mp3' % (os.path.join(os.environ['HOME'], SETTINGS_DIR, chan_data['uuid']), )

    if not os.path.isfile(tts_file_name):
        text_to_speech_file(chan_data['name'], tts_file_name)

    return tts_file_name


##########################################################################################
def get_tvh_chan_urls():
    ''' gets the channel listing and generates an ordered dict
        returns dict: key = channel name, value = stream URL
    '''

    global DBG_LEVEL

    ts_url = MY_SETTINGS[SETTINGS_SECTION][TS_URL]
    ts_user = MY_SETTINGS[SETTINGS_SECTION][TS_USER]
    ts_pass = MY_SETTINGS[SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s?limit=400' % (
        ts_url,
        TS_URL_CHN,
    )
    ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    #print('<!-- get_tvh_chan_urls URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return {}

    ts_json = ts_response.json()
    if DBG_LEVEL > 1:
        print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    if TS_PAUTH in MY_SETTINGS[SETTINGS_SECTION]:
        ts_pauth = '&AUTH=%s' % (MY_SETTINGS[SETTINGS_SECTION][TS_PAUTH], )
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

            chan_map[chan_name] = '%s/%s/%s?profile=audio-only%s' % (
                                   MY_SETTINGS[SETTINGS_SECTION][TS_URL],
                                   TS_URL_STR,
                                   entry['uuid'],
                                   ts_pauth, )

    if DBG_LEVEL > 0:
        print('%s' % json.dumps(chan_map, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    return dict(sorted(chan_map.items()))


##########################################################################################
def check_load_config_file(settings_dir, settings_file):
    '''check there's a config file which is writable;
       returns 0 if OK, -1 if the rest of the page should be aborted,
       > 0 to trigger rendering of the settings page'''

    global DBG_LEVEL
    global MY_SETTINGS

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

    if not MY_SETTINGS.read(settings_file):
        error_text = 'Error, failed parse config file "%s"' % (settings_file, )
        return(-1, error_text)

    #print('Debug, check_load_config_file TVH url is %s'
    #      % (MY_SETTINGS[SETTINGS_SECTION][TS_URL], ) )

    return (0, 'OK')



##########################################################################################
# settings_editor
def settings_editor(settings_file):
    ''' settings_editor '''

    global DBG_LEVEL
    global MY_SETTINGS

    if SETTINGS_SECTION not in MY_SETTINGS.sections():
        print('section %s doesn\'t exit' % SETTINGS_SECTION)
        MY_SETTINGS.add_section(SETTINGS_SECTION)

    print('=== Settings ===')

    # attempt to find the value of each setting, either from the params
    # submitted by the browser, or from the file, or from the defaults
    for setting in SETTINGS_DEFAULTS:
        setting_value = ''

        try:
            setting_value = str(MY_SETTINGS.get(SETTINGS_SECTION, setting))
        except configparser.NoOptionError:
            if DFLT in SETTINGS_DEFAULTS[setting]:
                setting_value = SETTINGS_DEFAULTS[setting][DFLT]
            else:
                setting_value = ''

        print('Hint: %s' % (SETTINGS_DEFAULTS[setting][HELP], ))
        print('%s [%s]: ' % (SETTINGS_DEFAULTS[setting][TITLE], setting_value, ), end='')
        sys.stdout.flush()
        new_value = sys.stdin.readline().rstrip()
        if new_value not in ('', '\n'):
            MY_SETTINGS.set(SETTINGS_SECTION, setting, new_value)
        else:
            MY_SETTINGS.set(SETTINGS_SECTION, setting, setting_value)
        print('')

    config_file_handle = open(settings_file, 'w')
    if config_file_handle:
        MY_SETTINGS.write(config_file_handle)
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

    global DBG_LEVEL
    global MY_SETTINGS

    play_cmd = MY_SETTINGS.get(SETTINGS_SECTION, TS_PLAY)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(audio_file_name)
    #print('Debug, play command is "%s"' % (' : '.join(play_cmd_array), ))

    subprocess.call(play_cmd_array)


##########################################################################################
# play_channel
def play_channel(stream_url):
    ''' starts playing stream in a sub process
        if it sees STOP_PLAYBACK then it kills the player '''

    global DBG_LEVEL
    global MY_SETTINGS
    global PLAYER_PID
    global CHANNEL_PLAYING
    global STOP_PLAYBACK

    url = stream_url

    play_cmd = MY_SETTINGS.get(SETTINGS_SECTION, TS_PLAY)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(url)
    print('Debug, play command is "%s"' % (' : '.join(play_cmd_array), ))

    player_proc = subprocess.Popen(play_cmd_array, shell=False)
    PLAYER_PID = player_proc.pid
    print(str(player_proc) )
    print('player pid %d' % (PLAYER_PID, ))
    player_active = True
    while player_active:
        try:
            player_proc.wait(timeout=1)
            #print('Player finished')
            player_active = False
            STOP_PLAYBACK = False
            PLAYER_PID = 0

        except subprocess.TimeoutExpired:
            pass
            #print('Player still running')

        if STOP_PLAYBACK:
            player_proc.kill()

    print('play_channel exiting')
    CHANNEL_PLAYING = ''

##########################################################################################
# SIGINT/ctrl-c handler
def sigint_handler(_signal_number, _frame):
    ''' called when signal 2 or CTRL-C hits process, simply flags request to quit '''

    global DBG_LEVEL
    global EVENT
    global QUIT_FLAG

    print('\nCTRL-C QUIT')
    QUIT_FLAG = True
    EVENT.set()


##########################################################################################
def keyboard_listen_thread():
    ''' keyboard listening thread, sets raw input and uses sockets to
        get single key strokes without waiting, triggering an event. '''

    global KEY_STROKE
    global QUIT_FLAG

    # set term to raw, so doesn't wait for return
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    while QUIT_FLAG == 0:
        # a bit ugly, but use a timeout just to occasionally check QUIT_FLAG
        readable_sockets, _o, _e = select.select([sys.stdin], [], [], KEYBOARD_POLL_TIMEOUT)
        if readable_sockets:
            KEY_STROKE = sys.stdin.read(1)
            EVENT.set()

    # set term back to cooked
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


##########################################################################################
def save_favourites(list_data):
    ''' saves the current favourites to a file '''

    write_list_file(FAVOURITES_HDR,
                    os.path.join(os.environ['HOME'],SETTINGS_DIR, FAVOURITES_LIST),
                    list_data)

##########################################################################################
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    ''' minimal http request handler for remote control '''

    global CHANNEL_NEXT
    global CHANNEL_PLAYING
    global EVENT
    global KEY_STROKE
    global PLAYER_PID
    global RADIO_MODE
    global STOP_PLAYBACK

    def do_GET(self):   # pylint:disable=invalid-name
        ''' implement the http GET method '''

        global CHANNEL_NEXT
        global CHANNEL_PLAYING
        global KEY_STROKE
        global EVENT
        global PLAYER_PID
        global RADIO_MODE
        global STOP_PLAYBACK

        self.send_response(200)
        self.end_headers()
        # look for the letter after the "GET /"
        uri = self.requestline[5]
        if uri in valid_web_commands:
            KEY_STROKE = uri
            EVENT.set()
            time.sleep(0.5)

        if PLAYER_PID != 0:
            if STOP_PLAYBACK:
                status_playing = 'playing: %s but stopping soon\n' % CHANNEL_PLAYING
            else:
                status_playing = 'playing: %s\n' % CHANNEL_PLAYING
        else:
            status_playing = ''

        if CHANNEL_NEXT != '':
            channel_next = 'playing next: %s\n' % CHANNEL_NEXT
        else:
            channel_next = ''

        status_complete = '<b>Status</b><pre>radio mode: %s\n%s%s\n</pre>' % (RM_TEXT[RADIO_MODE], status_playing, channel_next, )

        favicon_url = '%s/favicon.ico' % (MY_SETTINGS[SETTINGS_SECTION][TS_URL], )
        self.wfile.write(bytearray(WEB_HOME % (favicon_url, status_complete, ), encoding ='ascii'))

##########################################################################################
def start_web_listener(httpd):
    ''' a very primitive web interface for remote control '''

    global KEY_STROKE
    global QUIT_FLAG

    print('Debug. starting httpd server')
    httpd.serve_forever()   # never returns

##########################################################################################
def radio_app():
    '''this runs the radio appliance'''

    global CHANNEL_NEXT
    global CHANNEL_PLAYING
    global DBG_LEVEL
    global EVENT
    global KEY_STROKE
    global MY_SETTINGS
    global PLAYER_PID
    global QUIT_FLAG
    global RADIO_MODE
    global STOP_PLAYBACK

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
        RADIO_MODE = RM_TVH

    # get the TVH channel map into the same format dict as the streams and favourites
    tvh_chan_map = get_tvh_chan_urls()

    if RADIO_MODE == RM_TVH:
        print('tvh radio mode')
        chan_map = tvh_chan_map
    elif RADIO_MODE == RM_STR:
        print('streaming radio mode')
        chan_map = streams_chan_map
    elif RADIO_MODE == RM_FAV:
        print('favourites radio mode')
        chan_map = favourites_chan_map
    else:
        print('Error, invalid radio mode')
        sys.exit(1)

    # sort and count channels for whatever mode we're in
    chan_names = list(chan_map.keys())  # get an indexable array
    max_chan = len(chan_map)            # max channel number

    chan_num = 0                        # start at first channel
    CHANNEL_NEXT = chan_names[chan_num]

    ####
    # now we have the data, lets do the radio thing!

    # trap ctrl-x/sigint so we can clean up
    signal.signal(signal.SIGINT, sigint_handler)

    # start a thread to listen to the keyboard
    threads = []
    threads.append(Thread(target=keyboard_listen_thread))
    threads[-1].start()

    # do we need to start a thread to act as the web server?
    ts_wport = MY_SETTINGS.get(SETTINGS_SECTION, TS_WPORT)
    if ts_wport and ts_wport != '' and ts_wport.isnumeric():
        httpd = HTTPServer(('localhost', int(ts_wport)), SimpleHTTPRequestHandler)
        threads.append(Thread(target=start_web_listener, args=(httpd, )))
        threads[-1].start()



    print('Playing next: %s' % (chan_names[chan_num], ))
    # SIGINT and keyboard strokes and (one day) GPIO events all get funnelled here
    while not QUIT_FLAG:
        EVENT.wait() # Blocks until the flag becomes true.
        if KEY_STROKE != '':
            if KEY_STROKE == 'A':   # secret key code :-)
                api_test_func()

            elif KEY_STROKE in ('?', 'h'):
                print_help()

            #elif KEY_STROKE == 'l':
                #DBG_LEVEL and print('list')
                #print('list')
                #print(', '.join(chan_names))

            elif KEY_STROKE == 'd':
                DBG_LEVEL and print('down')
                if chan_num > 0:
                    chan_num = chan_num - 1

            elif KEY_STROKE == 'e':
                DBG_LEVEL and print('e')
                streams_editor()

            elif KEY_STROKE == 'f':
                DBG_LEVEL and print('favourite')
                if chan_names[chan_num] in favourites_chan_map:
                    print('Removing channel %s to favourites' % (chan_names[chan_num], ))
                    del favourites_chan_map[chan_names[chan_num]]
                else:
                    print('Adding channel %s to favourites' % (chan_names[chan_num], ))
                    favourites_chan_map[chan_names[chan_num]] = chan_map[chan_names[chan_num]]
                    favourites_chan_map = dict(sorted(favourites_chan_map.items()))
                # re-count the channels
                if RADIO_MODE == RM_FAV:
                    max_chan = len(chan_map)
                    chan_names = list(chan_map.keys())  # get an indexable array

                save_favourites(favourites_chan_map)

            elif KEY_STROKE == 'F':
                DBG_LEVEL and print('F')
                if favourites_chan_map:
                    print('Favourites:')
                    print_channel_list('\t', favourites_chan_map)
                else:
                    print('Warning, no favourites set')


            elif KEY_STROKE == 'm':
                DBG_LEVEL and print('mode')
                # if changing mode, kill a running player
                while PLAYER_PID != 0:
                    print('Waiting to stop playback before changing mode')
                    STOP_PLAYBACK = True
                    CHANNEL_PLAYING = ''
                    time.sleep(1)

                # cycle between modes and choose the channel map for new mode
                if RADIO_MODE == RM_TVH:
                    RADIO_MODE = RM_STR
                    chan_map = streams_chan_map

                elif RADIO_MODE == RM_STR:
                    RADIO_MODE = RM_FAV
                    chan_map = favourites_chan_map

                elif RADIO_MODE == RM_FAV:
                    RADIO_MODE = RM_TVH
                    chan_map = tvh_chan_map
                else:
                    print('Error, mode change went wrong!')

                print('Debug, mode is now %s' % (RADIO_MODE,))
                chan_num = 0                        # start at first channel
                chan_names = list(chan_map.keys())  # get an indexable array
                max_chan = len(chan_map)            # max channel number


            elif KEY_STROKE == 'p':
                DBG_LEVEL and print('play')
                if PLAYER_PID == 0:
                    CHANNEL_PLAYING = chan_names[chan_num]
                    print('attempting to play channel %d/%s' % (chan_num, chan_names[chan_num],))
                    stream_url = chan_map[chan_names[chan_num]]
                    threads = []
                    threads.append(Thread(target=play_channel, args=(stream_url, ) ))
                    threads[-1].start()
                else:
                    print('Setting STOP_PLAYBACK true')
                    STOP_PLAYBACK = True
                    CHANNEL_PLAYING = ''

            elif KEY_STROKE == 'q':
                print('Quit!')
                while PLAYER_PID != 0:
                    print('Waiting to stop playback')
                    STOP_PLAYBACK = True
                    time.sleep(1)
                    CHANNEL_PLAYING = ''

                QUIT_FLAG = 1

            elif KEY_STROKE == 's':
                tts_file = chan_data_to_tts_file(chan_map[chan_names[chan_num]])
                play_file(tts_file)

            elif KEY_STROKE == 't':
                play_time()

            elif KEY_STROKE == 'u':
                DBG_LEVEL and print('up')
                if chan_num < max_chan - 1:
                    chan_num = chan_num + 1

            elif KEY_STROKE == 'm':
                if RADIO_MODE == RM_TVH:
                    RADIO_MODE = RM_STR
                else:
                    RADIO_MODE = RM_TVH
                    get_tvh_chan_urls()
                print('Mode now %s' % (RADIO_MODE, ))

            else:
                print('Unknown key')

            KEY_STROKE = ''
        else:
            print('Error, key "%s"' % (KEY_STROKE,))

        print('Playing next: %s' % (chan_names[chan_num], ))
        CHANNEL_NEXT = chan_names[chan_num]
        EVENT.clear() # Resets the flag.

    if httpd:
        print('Waiting for web service to shut down')
        httpd.shutdown()
        time.sleep(1)

    for thread in threads:
        print('Debug, joining thread to this')
        thread.join()


##########################################################################################
def main():
    '''the main entry point'''

    global CHANNEL_NEXT
    global CHANNEL_PLAYING
    global DBG_LEVEL
    global EVENT
    global KEY_STROKE
    global MY_SETTINGS
    global PLAYER_PID
    global RADIO_MODE
    global SETTINGS_DIR
    global SETTINGS_FILE
    global STOP_PLAYBACK

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
        DBG_LEVEL += 1
        print('Debug, increased debug level to %d' % (DBG_LEVEL, ))

    if args.setup or config_bad < 0:
        if config_bad < -1:
            print('Error, severe problem with settings, please fix and restart program')
            print('%s' % (error_text,) )
            sys.exit(1)
        if config_bad < 0:
            print('%s' % (error_text,) )
        settings_editor(settings_file)
    else:
        radio_app()


##########################################################################################

if __name__ == "__main__":
    DBG_LEVEL = 0
    KEY_STROKE = ''
    PLAYER_PID = 0
    CHANNEL_NEXT = ''
    CHANNEL_PLAYING = ''
    QUIT_FLAG = False
    STOP_PLAYBACK = False

    EVENT = Event()
    MY_SETTINGS = configparser.ConfigParser()
    main()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
