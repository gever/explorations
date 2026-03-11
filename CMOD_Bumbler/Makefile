# Makefile for Bumbler
# Uses arduino-cli to build and upload the sketch.
# Ensure arduino-cli is installed: https://arduino.github.io/arduino-cli/latest/

# Board definition (Arduino Nano)
BOARD = arduino:avr:nano
# Override PORT via command line if needed: make upload PORT=/dev/ttyUSB1
PORT ?= /dev/ttyUSB0
SKETCH = Bumbler

.PHONY: all compile upload clean monitor install-core

all: compile

install-core:
	arduino-cli core install arduino:avr

compile:
	arduino-cli compile --fqbn $(BOARD) $(SKETCH)

upload:
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) $(SKETCH)

monitor:
	arduino-cli monitor -p $(PORT) -c baudrate=115200

clean:
	rm -rf $(SKETCH)/build/
