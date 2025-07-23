# ProxiTalk Hardware Build Guide

This guide covers the physical assembly and wiring connections needed to build a ProxiTalk handheld device. Follow these steps carefully to ensure proper connections and functionality.

## Table of Contents
1. [Required Components](#required-components)
2. [3D Printing the Case](#3d-printing-the-case)
3. [Tools Needed](#tools-needed)
4. [Safety Precautions](#safety-precautions)
5. [Step-by-Step Assembly](#step-by-step-assembly)

## Required Components

### Main Components
- **Raspberry Pi Zero 2W** - Main computing unit
- **SSD1309 OLED Display** (128x64) - Primary display
- **Adafruit PowerBoost 1000C** - Battery management and 5V power supply
- **Adafruit I2S 3W Stereo Speaker Bonnet** - Audio output board
- **3.7V LiPo Battery** (1000mAh+ recommended)
- **Small speakers** (3W, 4Ω impedance)
- **SPDT Slide Switch** - Power control switch
- **USB-C Breakout Board** - For USB charging and power input

### Additional Components
- **Enclosure/case** (3D printed or purchased)
- **Heat Sink** for Raspberry Pi (optional technically but very recommended)
- **Jumper wires** (various colors for easy identification)
- **Heat shrink tubing** or electrical tape

## 3D Printing the Case

The ProxiTalk case is designed to be 3D printed using PLA filament. The case files are available in multiple formats to support different 3D printers and slicers.

### Available Case Files

The case consists of 5 separate parts [located in the `../wiki/case-files/` directory](https://github.com/lcraver/ProxiTalk/tree/main/wiki/case-files):

| File Name | Description | Purpose |
|-----------|-------------|---------|
| `ProxiTalk - Top.obj` | Top faceplate | Main top piece with display window |
| `ProxiTalk - Top Color.obj` | Top faceplate Accent Color | Optional colored accent piece |
| `ProxiTalk - Middle.obj` | Middle frame section | Houses screen and keyboard |
| `ProxiTalk - Bottom.obj` | Bottom shell | Contains the bulk of the device and access ports |
| `ProxiTalk - Power Switch.obj` | Power switch actuator | Actuates the internal slide switch |
| `ProxiTalk - Bambu [All].3mf` | Complete Bambu project | All parts pre-arranged for Bambu printers |

## Step-by-Step Assembly

### Step 1: Audio Board Connection

First, we'll attach the audio board to the Raspberry Pi.

![Audio Board Attached to Pi](../wiki/imgs/build/audio%20board%20attached%20to%20pi.jpg)
> Key connections you must make

### For Screen (Orange)
- SDL (Pin 3) → I2C Data
- SCL (Pin 5) → I2C Clock
- 3.3V (Pin 1) → For 3.3V power
### For Audio (Yellow)
- GPIO 18 (Pin 12) → I2S BCLK (Bit Clock)
- GPIO 19 (Pin 35) → I2S LRCLK (Left/Right Clock)  
- GPIO 21 (Pin 40) → I2S DIN (Data In)
### For Power (Green)
- 5V (Pin 2) → For 5V power
- GND (Pin 6) → Ground connection

### Step 2: Create Custom Connection Wires

![5V to Pi Connection](../wiki/imgs/build/5v%20to%20pi.jpg)
> 5V to Pi Connection Wire (male to female jumper wire)

![USB to PowerBoost](../wiki/imgs/build/usb%20to%20powerboost.jpg)
> USB to PowerBoost Connection Wire (female to female jumper wire)

![Ground Wire](../wiki/imgs/build/ground%20wire.jpg)
> Ground Wire Connection (male to female (2x) jumper wire)

Next, we'll set up the power management system using the PowerBoost 1000C.

**General Connections:**

1. **5V Power Output:**
   - Connect PowerBoost **5V** output to Pi **5V** pin (Pin 4) via the 5V to Pi Connection Wire (male to female jumper wire)

2. **Ground Connection:**
   - Connect PowerBoost **GND** to Pi **GND** pin (Pin 34) via the Ground Wire Connection (male to female (2x) jumper wire) as well as to the USB-C breakout board's ground pin.

3. **USB Input:**
   - Connect USB-C breakout board to PowerBoost **USB** input for charging via the USB to PowerBoost Connection Wire (female to female jumper wire)

### Step 5: Internal Assembly View

![Full Build Opened](../wiki/imgs/build/full%20build%20opened.jpg)

### Step 6: Detailed Internal Wiring

![Full Build Opened Close Up](../wiki/imgs/build/full%20build%20opened%20close%20up.jpg)

### Step 7: Final Assembly

![Full Build](../wiki/imgs/build/final.jpg)