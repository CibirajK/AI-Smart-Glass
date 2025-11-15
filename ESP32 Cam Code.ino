#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <driver/i2s.h>
#include <time.h>  // Required for time functions
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include <AudioGeneratorMP3.h>
#include <AudioFileSourceHTTPStream.h>
#include <AudioFileSourceBuffer.h>
#include <AudioOutputI2S.h>

// WiFi Credentials
const char* ssid = "Cibiraj";    
const char* password = "cibiraj123"; 

// Server API Endpoint
const char* serverUrl = "http://192.168.90.155:8000/upload";  // <-- Change this

// GPIO Pins
#define BUTTON_GPIO 13
#define LED_GPIO 4  // ESP32-CAM onboard flash LED

// MAX98357A Pins
#define I2S_DOUT 14  // Data out pin
#define I2S_BCLK 15  // Bit clock pin
#define I2S_LRC 16   // Word select (LRCLK) pin (changed to 16 to avoid button on 13)

// I2S Configuration
#define I2S_SAMPLE_RATE 16000
#define I2S_CHANNELS 1
#define I2S_BITS_PER_SAMPLE 16
#define DMA_BUFFER_COUNT 8
#define DMA_BUFFER_LEN 1024

// Camera GPIO Pins for AI-Thinker ESP32-CAM
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM    5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

// Button state variables for debouncing
bool lastButtonState = HIGH;
bool buttonPressed = false;
unsigned long lastDebounceTime = 0;
unsigned long debounceDelay = 50;

// Upload state management
bool isUploading = false;
unsigned long lastUploadTime = 0;
const unsigned long uploadCooldown = 1000; // 1 second cooldown between uploads

// Audio objects
AudioGeneratorMP3 *mp3 = nullptr;
AudioFileSourceHTTPStream *file = nullptr;
AudioFileSourceBuffer *buff = nullptr;
AudioOutputI2S *out = nullptr;

void setupI2S() {
  Serial.println("🎵 Initializing I2S...");
  
  const i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = I2S_SAMPLE_RATE,
    .bits_per_sample = (i2s_bits_per_sample_t)I2S_BITS_PER_SAMPLE,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S_MSB,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = DMA_BUFFER_COUNT,
    .dma_buf_len = DMA_BUFFER_LEN,
    .use_apll = false,
    .tx_desc_auto_clear = true,
    .fixed_mclk = 0
  };

  const i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_BCLK,
    .ws_io_num = I2S_LRC,
    .data_out_num = I2S_DOUT,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  Serial.printf("📌 I2S Pins: BCLK=%d, LRC=%d, DOUT=%d\n", I2S_BCLK, I2S_LRC, I2S_DOUT);

  esp_err_t err = i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("❌ Failed to install I2S driver: %d\n", err);
    return;
  }

  err = i2s_set_pin(I2S_NUM_0, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("❌ Failed to set I2S pins: %d\n", err);
    return;
  }

  i2s_start(I2S_NUM_0);
  Serial.println("✅ I2S initialized successfully");
  
  // Play a short test tone
  playTestTone();
}

void playTestTone() {
  Serial.println("🔊 Playing test tone...");
  
  // Generate a 440 Hz sine wave for 1 second
  const int duration = 1; // seconds
  const int samples = I2S_SAMPLE_RATE * duration;
  const float frequency = 440.0; // Hz (A4 note)
  
  for(int i = 0; i < samples; i++) {
    float t = (float)i / I2S_SAMPLE_RATE;
    float value = sin(2 * PI * frequency * t);
    
    // Convert to 16-bit PCM
    int16_t sample = (int16_t)(value * 32767);
    
    // Write sample to I2S
    size_t bytes_written;
    i2s_write(I2S_NUM_0, &sample, sizeof(sample), &bytes_written, portMAX_DELAY);
    
    if (i % (I2S_SAMPLE_RATE/4) == 0) { // Print progress every 1/4 second
      Serial.print(".");
    }
  }
  
  Serial.println("\n✅ Test tone complete");
}

void playAudioFromHTTP(String audioUrl) {
  Serial.println("📥 Starting audio download from: " + audioUrl);
  
  HTTPClient http;
  http.begin(audioUrl);
  http.addHeader("Accept", "audio/wav");
  int httpCode = http.GET();

  Serial.printf("📡 HTTP Response: %d\n", httpCode);

  if (httpCode == 200) {
    WiFiClient* stream = http.getStreamPtr();
    uint8_t buffer[DMA_BUFFER_LEN];
    int totalBytesRead = 0;
    
    // Skip WAV header (44 bytes)
    stream->readBytes(buffer, 44);
    Serial.println("⏭️ Skipped WAV header");
    
    // Read and play audio data
    while (http.connected() && (stream->available() > 0)) {
      size_t bytesRead = stream->readBytes(buffer, DMA_BUFFER_LEN);
      if (bytesRead > 0) {
        size_t bytesWritten = 0;
        esp_err_t err = i2s_write(I2S_NUM_0, buffer, bytesRead, &bytesWritten, portMAX_DELAY);
        if (err != ESP_OK) {
          Serial.printf("❌ Error writing to I2S: %d\n", err);
          break;
        }
        totalBytesRead += bytesRead;
        
        // Print progress every 32KB
        if (totalBytesRead % 32768 == 0) {
          Serial.printf("🎵 Playing audio... %d bytes processed\n", totalBytesRead);
        }
      }
    }
    Serial.printf("✅ Audio playback complete. Total bytes: %d\n", totalBytesRead);
  } else {
    Serial.printf("❌ Failed to download audio. HTTP code: %d\n", httpCode);
  }
  http.end();
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  
  Serial.begin(115200);
  pinMode(BUTTON_GPIO, INPUT_PULLUP);
  pinMode(LED_GPIO, OUTPUT);
  digitalWrite(LED_GPIO, LOW);  // turn off flash

  Serial.println("🚀 ESP32-CAM Booting...");

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ Connected to WiFi");

  // Setup NTP time for timestamps
  configTime(19800, 0, "pool.ntp.org");

  Serial.print("⏳ Waiting for NTP time...");
  struct tm timeinfo;
  int retries = 0;
  while (!getLocalTime(&timeinfo) && retries < 10) {
    Serial.print(".");
    delay(500);
    retries++;
  }
  if (retries >= 10) {
    Serial.println("\n❌ Failed to get time after retries");
  } else {
    Serial.println("\n✅ Time initialized");
  }

  // Camera Configuration
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_SVGA;  
  config.jpeg_quality = 10;
  config.fb_count = 1;

  // Init camera
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera Init Failed! Error code: 0x%x\n", err);
    return;
  }

  // Optimize camera settings for better OCR
  sensor_t * s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 1);     // Slightly brighter for better text recognition
    s->set_contrast(s, 1);       // Slightly more contrast
    s->set_saturation(s, 0);     // Normal saturation
    s->set_whitebal(s, 1);       // Enable white balance
    s->set_awb_gain(s, 1);       // Enable auto white balance gain
    s->set_exposure_ctrl(s, 1);  // Enable auto exposure
    s->set_gain_ctrl(s, 1);      // Enable auto gain
    s->set_agc_gain(s, 2);       // Slightly higher gain for better visibility
    s->set_bpc(s, 1);           // Enable bad pixel correction
    s->set_wpc(s, 1);           // Enable white pixel correction
    s->set_raw_gma(s, 1);       // Enable gamma correction
    s->set_lenc(s, 1);          // Enable lens correction
    s->set_hmirror(s, 0);       // No mirror
    s->set_vflip(s, 0);         // No flip
    s->set_dcw(s, 1);           // Enable downsize
    s->set_colorbar(s, 0);      // No colorbar
  }

  setupI2S();
  Serial.println("✅ System ready! Playing test tone...");
  playTestTone();
  Serial.println("✅ Ready for image capture!");
}

void loop() {
  unsigned long currentTime = millis();
  
  // Read button state with proper debouncing
  int reading = digitalRead(BUTTON_GPIO);
  
  if (reading != lastButtonState) {
    lastDebounceTime = currentTime;
  }
  
  if ((currentTime - lastDebounceTime) > debounceDelay) {
    if (reading != buttonPressed) {
      buttonPressed = reading;
      
      if (buttonPressed == LOW && !isUploading && (currentTime - lastUploadTime) > uploadCooldown) {
        Serial.println("🔘 Button Pressed - Capturing image...");
        captureAndSendImage();
        lastUploadTime = currentTime;
      }
    }
  }
  
  lastButtonState = reading;
  
  delay(10); // Small delay for stability
}

void captureAndSendImage() {
  if (isUploading) {
    Serial.println("⚠️ Already uploading, please wait...");
    return;
  }

  isUploading = true;

  // Flash LED to indicate capture
  digitalWrite(LED_GPIO, HIGH);
  delay(100);

  // FLUSH THE CAMERA BUFFER (grab and release 2-3 frames)
  for (int i = 0; i < 2; i++) {
    camera_fb_t *flush_fb = esp_camera_fb_get();
    if (flush_fb) esp_camera_fb_return(flush_fb);
    delay(30); // small delay to allow new frame
  }

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Camera capture failed");
    digitalWrite(LED_GPIO, LOW);
    isUploading = false;
    return;
  }

  digitalWrite(LED_GPIO, LOW);
  Serial.printf("📸 Image captured: %d bytes\n", fb->len);

  // Get current time for filename
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("❌ Failed to obtain time");
    esp_camera_fb_return(fb);
    isUploading = false;
    return;
  }

  char filename[40];
  strftime(filename, sizeof(filename), "esp32_%Y-%m-%d_%H-%M-%S.jpg", &timeinfo);

  // Start upload immediately without waiting
  uploadImageAsync(fb, filename);
}

void uploadImageAsync(camera_fb_t *fb, const char* filename) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi not connected");
    esp_camera_fb_return(fb);
    isUploading = false;
    return;
  }

  Serial.println("📤 Starting upload...");

  String boundary = "ESP32BOUNDARY";
  String bodyStart = "--" + boundary + "\r\n";
  bodyStart += "Content-Disposition: form-data; name=\"file\"; filename=\"" + String(filename) + "\"\r\n";
  bodyStart += "Content-Type: image/jpeg\r\n\r\n";
  String bodyEnd = "\r\n--" + boundary + "--\r\n";

  int totalLength = bodyStart.length() + fb->len + bodyEnd.length();
  uint8_t* fullBody = (uint8_t*)malloc(totalLength);
  if (!fullBody) {
    Serial.println("❌ Memory allocation failed");
    esp_camera_fb_return(fb);
    isUploading = false;
    return;
  }

  // Copy the parts
  memcpy(fullBody, bodyStart.c_str(), bodyStart.length());
  memcpy(fullBody + bodyStart.length(), fb->buf, fb->len);
  memcpy(fullBody + bodyStart.length() + fb->len, bodyEnd.c_str(), bodyEnd.length());

  // Send HTTP request
  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
  
  int responseCode = http.POST(fullBody, totalLength);

  if (responseCode > 0) {
    Serial.printf("✅ Upload successful! Response code: %d\n", responseCode);
    String response = http.getString();
    Serial.println("📝 Server response: " + response);

    String audioFile = response;
    String audioUrl = "http://192.168.90.155:8000/output_audio/" + audioFile;
    Serial.println("🔊 Playing Audio: " + audioUrl);
    playAudioFromHTTP(audioUrl);
  } else {
    Serial.printf("❌ Upload failed! Error: %s\n", http.errorToString(responseCode).c_str());
  }

  http.end();
  free(fullBody);
  esp_camera_fb_return(fb);
  isUploading = false;
  
  Serial.println("🎯 Ready for next capture!");
}

void setupAudio() {
  Serial.println("🎵 Initializing Audio...");
  
  // Create audio output object
  out = new AudioOutputI2S();
  out->SetPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  out->SetGain(1.0);  // Adjust volume (0.0 to 1.0)
  
  Serial.printf("📌 I2S Pins: BCLK=%d, LRC=%d, DOUT=%d\n", I2S_BCLK, I2S_LRC, I2S_DOUT);
  Serial.println("✅ Audio initialized");
}

void playAudioResponse(String imageFilename) {
  Serial.println("🎵 Fetching audio response...");
  
  // Clean up previous audio objects
  cleanupAudio();
  
  // Construct audio URL
  String audioUrl = String(serverUrl) + "/audio/" + imageFilename;
  Serial.println("🔗 Audio URL: " + audioUrl);
  
  // Create new audio objects
  file = new AudioFileSourceHTTPStream(audioUrl.c_str());
  buff = new AudioFileSourceBuffer(file, 2048);
  mp3 = new AudioGeneratorMP3();
  
  Serial.println("▶️ Starting playback...");
  
  // Begin playback
  if (mp3->begin(buff, out)) {
    while (mp3->isRunning()) {
      if (!mp3->loop()) {
        mp3->stop();
      }
    }
    Serial.println("✅ Playback complete");
  } else {
    Serial.println("❌ Failed to start MP3 playback");
  }
}

void cleanupAudio() {
  if (mp3) {
    mp3->stop();
    delete mp3;
    mp3 = nullptr;
  }
  if (buff) {
    delete buff;
    buff = nullptr;
  }
  if (file) {
    delete file;
    file = nullptr;
  }
}