# Complete Smart Glass System Wiring Guide

## System Overview
This system consists of:
1. **ESP32-CAM** - Captures images and uploads to server
2. **ESP32 Pico D4** - Receives audio and plays through I2S DAC
3. **MAX98357A I2S DAC** - Converts digital audio to analog
4. **Speaker** - Outputs the audio
5. **FastAPI Server** - Processes images with OCR and TTS

## Components Needed

### Hardware
- ESP32-CAM AI-Thinker module
- ESP32 Pico D4 module
- MAX98357A I2S DAC module
- Speaker (8Ω, 3W recommended)
- Breadboard and jumper wires
- USB cables for programming
- Power supply (5V/2A recommended)

### Software
- Arduino IDE with ESP32 board support
- Python with FastAPI server
- Required Python packages (see requirements.txt)

## Wiring Connections

### 1. ESP32-CAM to ESP32 Pico D4 (Serial Communication)
| ESP32-CAM Pin | ESP32 Pico D4 Pin | Description |
|---------------|-------------------|-------------|
| GPIO 16 (RX2) | GPIO 16 (RX2)     | Serial2 RX |
| GPIO 17 (TX2) | GPIO 17 (TX2)     | Serial2 TX |
| GND           | GND               | Ground |

### 2. MAX98357A I2S DAC to ESP32 Pico D4
| MAX98357A Pin | ESP32 Pico D4 Pin | Description |
|---------------|-------------------|-------------|
| VDD           | 3.3V              | Power supply |
| GND           | GND               | Ground |
| BCLK          | GPIO 26           | Bit clock |
| LRC           | GPIO 25           | Word select (LRCLK) |
| DIN           | GPIO 22           | Data input |
| GAIN          | 3.3V              | Gain control (3.3V = 15dB gain) |
| SD            | GND               | Shutdown (GND = enabled) |

### 3. Speaker to MAX98357A
| Speaker Wire | MAX98357A Pin | Description |
|--------------|---------------|-------------|
| + (Positive) | Speaker+      | Audio output positive |
| - (Negative) | Speaker-      | Audio output negative |

### 4. ESP32-CAM Power and Programming
| ESP32-CAM Pin | Connection | Description |
|---------------|------------|-------------|
| 5V            | 5V Power   | Power supply |
| GND           | GND        | Ground |
| U0R (GPIO 3)  | USB-TTL TX | Programming |
| U0T (GPIO 1)  | USB-TTL RX | Programming |
| GPIO 0        | GND        | Programming mode (connect to GND for upload) |

### 5. ESP32 Pico D4 Power and Programming
| ESP32 Pico D4 Pin | Connection | Description |
|-------------------|------------|-------------|
| VBUS             | 5V Power   | Power supply |
| GND              | GND        | Ground |
| U0T (GPIO 1)     | USB-TTL RX | Programming |
| U0R (GPIO 3)     | USB-TTL TX | Programming |

## Pin Definitions in Code

### ESP32-CAM (ESP32_CAM_Complete.ino)
```cpp
// Serial2 for communication with ESP32 Pico D4
#define SERIAL2_RX 16  // GPIO16
#define SERIAL2_TX 17  // GPIO17
```

### ESP32 Pico D4 (ESP32_Pico_D4_Complete.ino)
```cpp
// I2S Configuration for MAX98357A DAC
#define I2S_BCK_IO      26  // Bit clock
#define I2S_WS_IO       25  // Word select (LRCLK)
#define I2S_DO_IO       22  // Data out

// Serial2 for communication with ESP32-CAM
#define SERIAL2_RX 16  // GPIO16
#define SERIAL2_TX 17  // GPIO17
```

## Setup Instructions

### 1. Hardware Setup
1. **Connect ESP32-CAM to ESP32 Pico D4** via Serial2 (GPIO 16, 17)
2. **Connect MAX98357A DAC to ESP32 Pico D4** using I2S pins
3. **Connect speaker to MAX98357A DAC**
4. **Power both ESP32 modules** (5V supply recommended)
5. **Connect programming cables** for initial upload

### 2. Software Setup
1. **Install Arduino IDE** with ESP32 board support
2. **Install required libraries**:
   - ESP32 board package
   - ArduinoJson library
   - ESP32 camera library
3. **Upload ESP32_CAM_Complete.ino** to ESP32-CAM
4. **Upload ESP32_Pico_D4_Complete.ino** to ESP32 Pico D4

### 3. Server Setup
1. **Install Python requirements**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Start the FastAPI server**:
   ```bash
   python main.py
   ```
3. **Note the server IP address** displayed in console

### 4. Configuration
1. **Update WiFi credentials** in both Arduino files
2. **Update server IP address** in both Arduino files
3. **Test connections** using Serial Monitor

## Testing the System

### 1. Initial Testing
1. **Power on both ESP32 modules**
2. **Check Serial Monitor** for both devices
3. **Verify WiFi connections**
4. **Test server connectivity**

### 2. Image Capture Test
1. **ESP32-CAM should capture images** every 30 seconds
2. **Check server logs** for uploaded images
3. **Verify OCR processing** in server console
4. **Check audio generation** in output_audio folder

### 3. Audio Playback Test
1. **ESP32 Pico D4 should receive audio** via Serial2
2. **Check I2S DAC output** with speaker
3. **Verify audio quality** and volume
4. **Test fallback server polling** if needed

## Troubleshooting

### Common Issues

#### ESP32-CAM Issues
- **Camera not initializing**: Check pin connections and power supply
- **Upload failures**: Connect GPIO 0 to GND during upload
- **WiFi connection**: Verify credentials and network availability

#### ESP32 Pico D4 Issues
- **No audio output**: Check I2S connections and DAC power
- **Serial communication**: Verify Serial2 pin connections
- **I2S errors**: Check DAC wiring and power supply

#### Server Issues
- **OCR not working**: Install Tesseract OCR on system
- **TTS errors**: Check internet connection for gTTS
- **File permissions**: Ensure write access to folders

### Debug Commands
```cpp
// ESP32-CAM debug
Serial.println("Camera status: " + String(esp_camera_init(&config)));

// ESP32 Pico D4 debug
Serial.printf("I2S status: %d\n", i2s_driver_install(I2S_NUM, &i2s_config, 0, NULL));
```

## Performance Optimization

### Audio Quality
- **Sample rate**: 16kHz for speech, 44.1kHz for music
- **Buffer size**: 1024 bytes for smooth playback
- **DAC quality**: MAX98357A provides good audio quality

### Processing Speed
- **Image quality**: JPEG quality 10 for fast upload
- **Frame size**: VGA (640x480) for good OCR
- **Processing interval**: 30 seconds between captures

### Power Management
- **Deep sleep**: Can be added for battery operation
- **WiFi power**: Disconnect when not needed
- **I2S power**: Stop when not playing audio

## Future Enhancements

### Hardware Upgrades
- **Better camera**: Higher resolution for better OCR
- **Audio amplifier**: PAM8403 for louder output
- **Battery pack**: For portable operation
- **Display**: OLED for status information

### Software Features
- **Voice commands**: Speech recognition
- **Multiple languages**: Support for other languages
- **Cloud storage**: Save images and audio to cloud
- **Mobile app**: Control via smartphone

### Integration Options
- **Bluetooth headphones**: A2DP source functionality
- **WiFi speakers**: AirPlay or Chromecast
- **Smart home**: Integration with home automation
- **Cloud AI**: Use cloud-based OCR and TTS

ESP32 Pico D4 → Downloads audio from server → Plays through Bluetooth speakers 