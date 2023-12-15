# The tvh_TV Project

To use in a raspberry Pi 1b, 2 or 3, it requires:

+ Tvheadend running on a server (or on same pi)
+ MPEG-2 Hardware decoding 

https://github.com/tvheadend/

## Memory

GPU memory should be a minimum of 128MB in config.txt

    gpu_mem=128
    
## MPEG-2 decoding

It requires that the MPEG-2 hardware codec is enabled (by
purchase of the license). 

To activate (forgotten) mpeg2 and VC codec licenses on raspberry pi follow this:

[LINK](https://github.com/suuhm/raspi_mpeg_license_patch.sh)


## Usage

You can use this on a Pi, or a linux desktop or laptop, as it should run on
any linux distro which supports a modern python3.

The software here is a command line interface, so that the Pi can be used
headless with just a keyboard. This project will be expanded to include
instructions on fitting into a re-purposed radio shell, and setting the
Pi to boot straight into this application.


# Installation

## Pre-Requisites

Acquire a Raspberry Pi, power supply and memory card. 

* Install Raspbian onto the card
* Power up the Pi whilst connected to a display
* Configure the WiFi
* Set the password of the pi user
* Install all updates


## TV Headend

### Create a user with persistent authentication token

Create a user account with a password and persistent authentication like this:
![Audio-Only Profile](https://raw.githubusercontent.com/speculatrix/tvh_radio/master/tvh-user-entry.png)

Then create an access entry for thet use allowing playing media etc like this:
![Audio-Only Profile](https://raw.githubusercontent.com/speculatrix/tvh_radio/master/tvh-access-entry.png)



## Getting the program

* git clone this repository
* make tvh_tv.py executable if necessary with "chmod ugo+x tvh_tv.py"


## Running the program

* run it
* on first run, you have to go through setup, so provide the settings
* follow the onscreen instructions
* if you need to redo the settings, run it again with the -s option to go into settings


key functions

* ? - help
* d - down a channel
* h - help
* p - play channel/stop channel
* q - quit
* u - up a channel


