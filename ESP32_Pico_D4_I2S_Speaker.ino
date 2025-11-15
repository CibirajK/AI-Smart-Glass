#include <WiFi.h>
#include <HTTPClient.h>
#include <AudioGeneratorMP3.h>
#include <AudioFileSourceHTTPStream.h>
#include <AudioFileSourceBuffer.h>
#include <AudioOutputI2S.h>

const char* ssid = "Cibiraj";
const char* password = "cibiraj123";

// I2S pins matching physical wiring
#define I2S_DOUT 22  // Data Out (DIN on MAX98357A)
#define I2S_BCLK 26  // Bit Clock
#define I2S_LRC  25  // Left/Right Clock (Word Select)

// Audio objects
AudioGeneratorMP3 *mp3 = nullptr;
AudioFileSourceHTTPStream *file = nullptr;
AudioFileSourceBuffer *buff = nullptr;
AudioOutputI2S *out = nullptr;

void setupI2S() {
  // Initialize I2S output
  out = new AudioOutputI2S();
  out->SetPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  out->SetGain(1.0);  // Maximum volume
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

void playAudioFromURL(String audioFileName) {
  String audioUrl = "http://192.168.79.147:8000/output_audio/" + audioFileName;
  Serial.println("🔊 Fetching: " + audioUrl);

  // Clean up previous audio objects
  cleanupAudio();

  // Create new audio objects
  file = new AudioFileSourceHTTPStream(audioUrl.c_str());
  buff = new AudioFileSourceBuffer(file, 2048);
  mp3 = new AudioGeneratorMP3();

  // Start playback
  if (mp3->begin(buff, out)) {
    Serial.println("▶️ Starting playback...");
    while (mp3->isRunning()) {
      if (!mp3->loop()) {
        mp3->stop();
      }
    }
    Serial.println("✅ Playback complete");
  } else {
    Serial.println("❌ Failed to start playback");
  }

  cleanupAudio();
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  Serial.print("🔌 Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi Connected");

  setupI2S();
  Serial.println("🎧 Ready to receive filename...");
}

void loop() {
  static String audioFileName = "";

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      audioFileName.trim();
      if (audioFileName.endsWith(".wav") || audioFileName.endsWith(".mp3")) {
        playAudioFromURL(audioFileName);
      }
      audioFileName = "";
    } else {
      audioFileName += c;
    }
  }

  delay(10);
}
