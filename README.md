# The tvh_radio Project

A streaming TV client for a TV Headend server which will be expanded to
play other streams.

Formerly known as the Yet Another Pi Radio application before it took on a
life of its own.

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
* make tvh_radio.py executable if necessary with "chmod ugo+x tvh_radio.py"


## Running the program

* run it
* on first run, you have to go through setup, so provide the settings
* follow the onscreen instructions
* if you need to redo the settings, run it again with the -s option to go into settings


key functions

* ? - help
* d - down a channel
* f - favourite or unfavourite a channel
* F - favourites list
* h - help
* m - mode change, from TVH to stream to favourites
* p - play channel/stop channel
* q - quit
* s - speak channel name
* t - speak time
* u - up a channel

# Road Map

## Key/input customisation

I intend to make the key presses customisable, so you could, say, use a
numeric USB key pad to operate it. Also, to make it possible to use GPIOs
and switches instead of a USB button board, something like the Display-O-Tron Hat:
https://thepihut.com/collections/raspberry-pi-hats/products/display-o-tron-hat

I also intend to make it possible to use a small LCD display to give status.
