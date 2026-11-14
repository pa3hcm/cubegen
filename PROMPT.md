# PROMPT

This project was generated with the help of an AI model.

- **AI model:** Claude Opus 5.5 (model ID `claude-opus-5-5`) by Anthropic
- **Tool:** Claude Code (Claude desktop app, Code tab)
- **Date:** 2026-11-11

## Full prompt

> I want to create an RF signal generator, using the following components:
>
> * ESP32 devboard
> * SI5351 dds board with 25MHz crystal and 3 SMA outputs and I2C connection
> * GM009605v4 0.96 inch oled display with I2C connection
> * Small board with 4 pushbuttons with a common ground connection
>
> The display should start saying "sigblock v0.1b" and "(c) 2026 PA3HCM".
> After 2 seconds it should display "10.000.000", indicating the output is 10 MHz exactly. Just below the 1 should be a cursor, indicating that this digit is currently selected.
>
> The 4 buttons are numbered 1 to 4.
>
> * Button 1: increase the selected digit. If going from 9 to 10/0, upper the next digit 1 as well, for example, upping the right digit of '19' will not go back to '10' but to '20'.
> * Button 2: decrease the selected digit. It work the same as button 1, but then counting down.
> * Button 3: select the next digit. When on the last digit, move back to the first digit.
> * Button 4: Not used yet, will work on this later.
>
> Whenever the number on the display changes, the output frequency of the SI5351 should be changed to the displayed value.
>
> Create an image that displays the wiring between the boards.
>
> All boards are running on 3.3 volt.
>
> Store all code in a folder named 'cubegen'. Also create a file PROMPT.md with the used AI model and version and a full prompt representing this conversation. I will use VScode + PlatformIO to program the ESP32.

### Follow-up 1

> The cursor indicates the selected digit.

(Confirmed: this was already implemented, no change.)

### Follow-up 2

> Button 4 sets the mode. The following modes are available:
>
> * The default mode is `CW` which sends a continuous carrier
> * The next mode is `CW-keyed`, which sends a CW signal -.-.-. etc...
> * The next mode is `FSK470`, where the signal is alternating 500ms on the given frequency and 500ms on a frequency that is 470Hz higher
> * The next mode is `FSK850`, same as FSK470 but with 850Hz shift
> * The next mode is `FSK1K`, same as FSK470 bith with 1kHz shift
> * FInal mode is `OFF`, were no signal is generated.
>
> The display should show 'Mode: ' followed by the selected mode

### Follow-up 3

> Add a new mode `FSK10K`with 10kHz shift.

### Follow-up 4

> Change the default frequency from 10.000MHz to 10.100MHz. Set the default mode to `FSK10K`

### Follow-up 5

> How fast can you switch the SI5351 to another frequency? I try to key it every 100ms, but I don't know how realistic that is?

(Answered only, no code change: below 100 MHz a frequency change only rewrites the multisynth registers, < 1 ms.)

### Follow-up 6

> Change any reference to 'sigblock' to 'cubeGen'

(The original prompt above is kept verbatim; the splash screen then read "cubeGen v0.1b", later renamed to "QubeRG v0.1b".)

### Follow-up 7

> Set the default mode to FSK1K

### Follow-up 8

> Set the default frequency to 10.2 MHz

### Follow-up 9

> Set de default mode to CWkeyed

### Follow-up 10

> Set the default mode to `OFF`and the default frequency to 10.000 MHz.

### Follow-up 11

> Create a new repository on my Github (account: 'pa3hcm'). Push all code to this repository. You can use the github client on my laptop.

(Created public repository https://github.com/pa3hcm/cubegen, later renamed to https://github.com/pa3hcm/QubeRG.)

### Follow-up 12

> Apply the following license: Creative Commons Attribution-NonCommercial 4.0 International License

### Follow-up 13

> The software is ok for now. The next thing to do is designing a case. I have a 3D-printer (FDM) and want to print a case with PETG. The case has the shape of a cube. You should be able to open it, maybe the cube is in 2 halfs which you can click together. On top there will be the RF output, based on an SMA thru-hole screw connector F-F. The SI5351 board is screwed on the inside, using a M-M SMA adaptor. On one of the sides is the .96' display, on the opposite side are the buttons. On the bottom of the cube lays the ESP32 board, in such a way that the USB connector can be reached from the outside to power the whole unit. All boards should be mounted in such a way that they "click" in place or get locked in by closing the cube. Please generate the STL's and add them to the repository.

### Follow-up 14

> Rename the repository (and the current folder where it is stored) to `QubeRG`.

### Follow-up 15

> Also render a image to show the product as it would look like when built. Include this image in the introduction text of the README.md.

### Follow-up 16

> Search all code, text, drawings, etc for the name 'CubeGen' and replace that name with `'QubeRG'`

(Quoted prompts in this file are kept verbatim.)

## Design decisions made by the AI

- I2C bus shared by Si5351 (0x60) and OLED (SSD1306, 0x3C) on GPIO21 (SDA) / GPIO22 (SCL).
- Buttons on GPIO32, GPIO33, GPIO25, GPIO26 using the ESP32 internal pull-ups (buttons switch to GND).
- RF output on Si5351 CLK0; CLK1 and CLK2 disabled.
- Display shows 8 digits (`XX.XXX.XXX` Hz), so the range is limited to 8 kHz … 99.999.999 Hz.
  Steps that would leave this range are ignored.
- Buttons 1 and 2 auto-repeat when held down.
- Power-up defaults: 10.000.000 Hz, mode OFF, cursor on the first digit.
- Button 4 cycles CW → CW-keyed → FSK470 → FSK850 → FSK1K → FSK10K → OFF → CW (FSK10K placed after FSK1K).
- CW-keyed repeats "-." (dash 300 ms, gap 100 ms, dot 100 ms, gap 100 ms), i.e. 12 WPM.
- FSK modes start on the displayed frequency, then the shifted (higher) frequency.
- Keying is done with the Si5351 output enable, so the oscillator keeps running.
- "Mode: <mode>" is shown on the bottom line of the display; a missing Si5351 warning moved to the top line.
- License: CC BY-NC 4.0; official legal code in `LICENSE`, notice in README, `main.cpp` and `platformio.ini`.
- Case: 90 mm cube, generated by a parametric Python script (`case/qube_case.py`, manifold3d) because OpenSCAD was not available; bottom part + top part with tongue and snap ridges.
- Case: ESP32 lies component side up with pins down, 22 mm above the floor for dupont plugs, held by 4 snap hooks at the PCB corners; USB on the left wall.
- Case: display and button board slide into rails and are held down by fingers on the lid; printed button caps with a flange.
- Case: Si5351 stands vertical (parallel to the side walls) at x = 72 mm, hanging from the SMA bulkhead, to stay clear of the ESP32 and its wiring.
- Case: board dimensions are assumptions (ESP32 DevKit 55x28, GM009605 27.3x27.8, Si5351 40x30, button board 45x20) and must be checked.
- Product render and inside view rendered with matplotlib (`case/qube_preview.py`).
- Libraries: Etherkit Si5351, Adafruit SSD1306, Adafruit GFX.
