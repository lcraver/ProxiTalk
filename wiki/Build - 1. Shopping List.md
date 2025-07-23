# Shopping List
These are the components required to make this build. All links are where I personally obtained them, but I have no affiliation with any of these sites. If you find the parts somewhere else, you can use them. However, please keep in mind that I cannot promise the setup/build instructions will remain exactly the same. If you have any questions about case mods or other modifications to the build, please don't hesitate to ask.

## Required

### Raspberry Pi Zero 2 W (Without Headers)
The brains of the whole operation. Please ensure you obtain one without headers; this will make the setup process much easier.
https://www.adafruit.com/piz2w

### Lithium Ion Polymer Battery - 3.7v 2500mAh
Used as the base power source for the entire device, you can use a slightly larger or smaller one if you wish; however, please note that the case was designed specifically for this exact model.
https://www.adafruit.com/product/328

### Adafruit PowerBoost 1000C
This is used in conjunction with the LiPo to charge/manage the battery, as well as the Pi's power, required for a complete portable experience.
https://www.adafruit.com/product/2465

### SPDT Slide Switch
A small, simple power switch used to turn the device (Powerboost 1000c specifically) on and off.
https://www.adafruit.com/product/805

### HiLetgo 2.42" SSD1309 128 by 64 Oled Display (I2C Version)
Please make sure you select the I2C version instead of the SPI for ease of setup. Any color is good, so pick your favorite!
https://www.amazon.com/dp/B0CFF3XNX4

### Random Wireless Bluetooth Keyboard
Picked due to its small size and fragile-looking shell (you have to crack it open to get to the nice insides that we actually want lol).
https://www.amazon.com/dp/B0C583RCXD

### Raspberry Pi Zero 2W Heatsink
Unfortunately, while the Pi does run mostly cool, I did end up needing a heatsink over long usage periods. This is the exact one I picked up!
https://www.amazon.com/dp/B09QMBCXLB

## Optional

### Adafruit I2S 3W Stereo Speaker Bonnet
This is used to have decent audio output for the device's speakers, as GPIO direct output was deemed too rough. If you don't want onboard speakers, this isn't required, but know that will mean you'll have to connect a Bluetooth speaker whenever you want to use it.
https://www.adafruit.com/product/3346

### Uxcell 4 Ohm 3W Speakers
These are the exact speakers I ended up going with; they have a good size-to-power ratio and sound quite good, despite their limitations.
https://www.amazon.com/dp/B082ZPP56D

### Raspberry PI GPIO Female Headers
I used this to make it easier to prototype and take apart. Technically, you could solder directly to the Pi, though!
https://www.amazon.com/dp/B07P57N3TZ

### USB C Breakout Board
Again, used for convenience and ease of use. I wanted USB-C on this device instead of the Micro USB that the 1000C PowerBoost comes with. Feel free to find a PowerBoost clone that has USB-C or simply live with the Micro USB; your choice.
https://www.amazon.com/dp/B096M2HQLK

## Misc Supplies
- Solder
- Wires
- Heat Shrink
- Hot Glue Stick
- Any 32+ GB Micro SD Card (for the DietPi install and ProxiTalk OS)

## Misc Tools
- Soldering Iron
- Automatic Wire Stripper (Optional, but it's nice to have)
- Hot Glue Gun
- Screwdriver
- Wire Cutters
- Needle Nose Pliers

## Full Costs
Everything from the places I bought them: **$127.56** (cost subject to change over time, of course).
Unfortunately, this cost ended up being a bit higher than expected. A future version made with a custom board would likely reduce the price significantly at scale. However, given that we have to buy so many discrete components, I couldn't see it getting much lower overall with this setup. If money is tight, consider cutting out the onboard audio and other optional features, and you can get it to be just under $100.